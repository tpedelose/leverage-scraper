# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html
from __future__ import annotations

import psycopg
import logging

from Leverage.items import UnitItem, PromoItem, PropertyItem
from psycopg import Rollback
from scrapy.exceptions import DropItem
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import Cursor
    from scrapy import Spider, Item
    from scrapy.crawler import Crawler


class PostgresConnectionPipeline:
    logger = logging.getLogger(__name__)

    def __init__(self, db_dsn: str):
        self.db_dsn = db_dsn
        self.conn = None

    @classmethod
    def from_crawler(cls, crawler: Crawler):
        db_dsn: str = crawler.settings.get("DB_DSN")
        cls.logger.info(f"PostgresConnectionPipeline using DSN: {db_dsn}")
        if not db_dsn:
            raise ValueError(
                "DB_DSN setting is required for PostgresConnectionPipeline."
            )
        return cls(db_dsn)

    def open_spider(self, spider: Spider):
        self.conn = psycopg.connect(self.db_dsn, autocommit=True)
        # expose connection so other pipelines can use it
        spider.crawler.postgres_conn = self.conn
        spider.logger.info("Postgres connection opened.")

    def close_spider(self, spider: Spider):
        conn = getattr(spider.crawler, "postgres_conn", None)
        if conn:
            conn.close()
            del spider.crawler.postgres_conn


class PropertyItemPipeline:
    logger = logging.getLogger(__name__)

    def process_item(self, item: Item, spider: Spider) -> Item:
        if not isinstance(item, PropertyItem):
            return item  # Pass through other item types

        conn: psycopg.Connection = getattr(spider.crawler, "postgres_conn")
        if not conn:
            raise ValueError("No PostgreSQL connection available in spider.")

        self.logger.info("Processing PropertyItem...")

        if "company_name" not in item:
            # TODO: Should I pass item through for potential later use?
            raise DropItem("PropertyItem missing company_name field.")
        company_name = item["company_name"]

        with conn.cursor() as cur:
            company_name = self.get_company_id(cur, company_name)
            _ = self.upsert_property(cur, item, company_name)

        return item

    def get_company_id(self, cur: Cursor, company_name: str) -> int:
        # NOTE: Can probably remove this method if company_id is provided directly in the PropertyItem, from the specific indexer
        sql = "SELECT company_id FROM management_companies WHERE name = %s;"
        cur.execute(sql, (company_name,))
        result = cur.fetchone()
        if not result:
            raise ValueError(
                f"Failed to retrieve company_id for company_name={company_name}"
            )
        return result[0]

    def upsert_property(self, cur: Cursor, item: PropertyItem, company_id: int) -> int:
        # Use a property URL or a combined City/Name as the ON CONFLICT target
        # TODO! Update primary key to something beyond the URL alone
        query = """
            INSERT INTO properties (
                company_id,
                property_name,
                url,
                template_engine,
                address,
                city,
                state,
                postal_code,
                updated_source
            )
            VALUES (
                %(company_id)s,
                %(name)s,
                %(url)s,
                %(template)s,
                %(address)s,
                %(city)s,
                %(state)s,
                %(postal_code)s,
                'scrape'::update_source_type
            )
            ON CONFLICT (url) DO UPDATE
            SET
                property_name = EXCLUDED.property_name,
                address = EXCLUDED.address,
                city = EXCLUDED.city,
                state = EXCLUDED.state,
                postal_code = EXCLUDED.postal_code,
                template_engine = EXCLUDED.template_engine,
                updated_source = 'scrape'::update_source_type
            RETURNING property_id;
        """
        # NOTE: PostgreSQL increments the counter on GENERATED ALWAYS AS IDENTITY columns on every insert attempt,
        # even if the insert fails due to a conflict. This is expected behavior.

        data = {
            "company_id": company_id,
            "name": item.get("property_name"),
            "url": item.get("url", "").rstrip("/"),
            "template": item.get("template_engine"),
            "address": item.get("address"),
            "city": item.get("city"),
            "state": item.get("state"),
            "postal_code": item.get("postal_code"),
        }

        cur.execute(query, data)
        result = cur.fetchone()
        if not result:
            raise ValueError(f"Failed to upsert property with URL={data['url']}")

        self.logger.info(f"Upserted property_id: {result[0]}")
        return result[0]


class UnitItemPipeline:
    logger = logging.getLogger(__name__)

    def process_item(self, item: Item, spider: Spider):
        if not isinstance(item, UnitItem):
            return item  # Pass through other item types

        conn = getattr(spider.crawler, "postgres_conn", None)
        if not conn:
            raise ValueError("No PostgreSQL connection available in spider.")

        self.logger.info("Processing UnitItem...")
        url = item.get("property_url")
        if not url:
            # TODO: Should I pass item through for potential later use?
            raise DropItem("No property URL in UnitItem.")

        with conn.cursor() as cur:
            property_id = self.get_property_id(cur, url)

            with conn.transaction():
                try:
                    floorplan_id = self.upsert_floorplan(cur, item, property_id)
                    unit_id = self.upsert_apartment_unit(
                        cur, item, property_id, floorplan_id
                    )
                    self.insert_price_history(cur, item, unit_id)

                except Exception as e:
                    self.logger.error(f"Transaction failed: {e}")
                    Rollback()  # Roll back all changes if any step fails
                    raise e

        return item

    def get_property_id(self, cur: Cursor, url: str) -> int:
        # SQL logic to retrieve property_id based on a natural key
        query = "SELECT property_id FROM properties WHERE url = %s;"
        cur.execute(query, (url,))
        result = cur.fetchone()
        if not result:
            raise ValueError(f"Failed to retrieve property_id for url={url}")
        return result[0]

    def upsert_floorplan(self, cur: Cursor, item: UnitItem, property_id: int) -> int:
        # TODO: Consider if DO UPDATE is needed here to update metadata
        # Check out this: https://stackoverflow.com/questions/34708509/how-to-use-returning-with-on-conflict-in-postgresql
        query = """
            WITH upsert AS (
                INSERT INTO floorplans (
                    property_id,
                    plan_name,
                    bedrooms,
                    bathrooms,
                    square_footage
                )
                VALUES (
                    %(prop_id)s,
                    %(plan_name)s,
                    %(bedrooms)s,
                    %(bathrooms)s,
                    %(square_footage)s
                )
                ON CONFLICT (property_id, plan_name) DO NOTHING
                RETURNING floorplan_id
            )
            SELECT floorplan_id FROM upsert
            UNION
                SELECT floorplan_id
                FROM floorplans
                WHERE (
                    property_id = %(prop_id)s
                    AND plan_name = %(plan_name)s
                );
        """

        data = {
            "prop_id": property_id,
            "plan_name": item.get("floorplan_name"),
            "bedrooms": item.get("num_bedrooms"),
            "bathrooms": item.get("num_bathrooms"),
            "square_footage": item.get("square_footage"),
        }

        cur.execute(query, data)
        result = cur.fetchone()
        if not result:
            raise ValueError(
                f"Failed to retrieve floorplan_id for property_id={property_id} and plan_name={item.get('floorplan_name')}"
            )

        self.logger.info(f"Upserted floorplan_id: {result[0]}")
        return result[0]

    def upsert_apartment_unit(
        self, cur: Cursor, item: UnitItem, property_id: int, floorplan_id: int
    ) -> int:
        query = """
            WITH upsert AS(
                INSERT INTO apartment_units (
                    property_id,
                    floorplan_id,
                    unit_number,
                    floor_number,
                    building_name,
                    is_on_top_floor
                )
                VALUES (
                    %(prop_id)s,
                    %(floorplan_id)s,
                    %(unit_number)s,
                    %(floor_number)s,
                    %(building_name)s,
                    %(is_on_top_floor)s
                )
                ON CONFLICT (property_id, building_name, unit_number) DO NOTHING 
                RETURNING unit_id
            )
            SELECT unit_id FROM upsert
            UNION
                SELECT unit_id
                FROM apartment_units
                WHERE (
                    property_id = %(prop_id)s 
                    AND building_name = %(building_name)s
                    AND unit_number = %(unit_number)s
                );
        """

        data = {
            "prop_id": property_id,
            "floorplan_id": floorplan_id,
            "unit_number": item.get("unit_number"),
            "floor_number": item.get("floor_number"),
            "building_name": item.get("building_name"),
            "is_on_top_floor": item.get("top_floor"),
        }

        cur.execute(query, data)
        result = cur.fetchone()
        if not result:
            raise ValueError(
                f"Failed to retrieve unit_id for property_id={property_id} and unit_number={item['unit_number']}"
            )

        self.logger.info(f"Upserted unit_id: {result[0]}")
        return result[0]

    def insert_price_history(self, cur: Cursor, item: UnitItem, unit_id: int) -> None:
        query = """
            INSERT INTO price_history (
                scraped_at,
                unit_id,
                rent_usd,
                deposit_usd,
                min_lease_term_months,
                is_available,
                available_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """

        data = (
            item.get("scraped_at"),
            unit_id,
            item.get("rent_usd"),
            item.get("deposit_usd"),
            item.get("min_lease_term_months"),
            item.get("is_available"),
            item.get("available_date"),
        )

        cur.execute(query, data)


class PromoItemPipeline:
    logger = logging.getLogger(__name__)

    def process_item(self, item: Item, spider: Spider):
        if not isinstance(item, PromoItem):
            return item  # Pass through other item types

        conn = getattr(spider.crawler, "postgres_conn", None)
        if not conn:
            raise ValueError("No PostgreSQL connection available in spider.")

        self.logger.info("Processing PromoItem...")

        with conn.cursor() as cur:
            _ = self.insert_promo(cur, item)

        return item

    def insert_promo(self, cur: Cursor, item: PromoItem) -> int:
        # SQL logic, often using ON CONFLICT to retrieve the existing floorplan_id
        # and cache it, so the ApartmentUnitItem can use it later.
        raise NotImplementedError("Method not yet implemented.")
