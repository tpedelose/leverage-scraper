# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

from Leverage.items import UnitItem, PromoItem, PropertyItem

import json
import psycopg2
import logging

from scrapy import Spider, Item
from scrapy.crawler import Crawler
from scrapy.exceptions import DropItem


class JsonPipeline:
    logger = logging.getLogger(__name__)
    pretty_print = True

    def open_spider(self, spider):
        self.file = open("items.jl", "w")

    def close_spider(self, spider):
        self.file.close()

    def process_item(self, item, spider):
        match self.pretty_print:
            case True:
                line = json.dumps(dict(item), indent=2) + "\n"
            case False:
                line = json.dumps(dict(item)) + "\n"
        self.file.write(line)
        return item


class PostgresPipeline:
    logger = logging.getLogger(__name__)

    def __init__(self, db_settings):
        self.db_config = db_settings
        self.conn = psycopg2.connect(**self.db_config)
        self.cur = self.conn.cursor()

    @classmethod
    def from_crawler(cls, crawler: Crawler):
        db_settings = crawler.settings.getdict("DATABASE_CONFIG")
        return cls(db_settings)

    def open_spider(self, spider: Spider):
        # Establish the connection when the spider starts
        try:
            if not self.conn or self.conn.closed:
                self.conn = psycopg2.connect(**self.db_config)
                self.conn.autocommit = False  # Ensure transactions are used
            if not self.cur or self.cur.closed:
                self.cur = self.conn.cursor()
            spider.logger.info("Successfully connected to PostgreSQL.")
        except psycopg2.Error as e:
            spider.logger.error(f"PostgreSQL connection failed: {e}")
            raise e

    def close_spider(self, spider: Spider):
        # Commit any remaining transactions and close the connection
        if self.conn:
            self.conn.commit()
            if self.cur:
                self.cur.close()
            self.conn.close()

    def process_item(self, item: Item, spider: Spider):
        try:
            match item:
                case PropertyItem():
                    self.logger.info("Processing PropertyItem...")
                    company_name = item.get("company_name")
                    if not company_name:
                        raise DropItem("PropertyItem missing company_url field.")
                    company_name = self._get_company_id(company_name)
                    property_id = self._upsert_property(item, company_name)

                case UnitItem():
                    self.logger.info("Processing UnitItem...")
                    try:
                        url = spider.start_urls[0]
                        self.logger.debug(url)
                        # TODO: Pass Item property_url field from spider to here to avoid issues with multiple start URLs
                    except IndexError:
                        raise DropItem(
                            "No start URL found in spider to determine property."
                        )

                    property_id = self._get_property_id(url)
                    self.process_unit_item(item, property_id)

                case PromoItem():
                    self.logger.info("Processing PromoItem...")
                    # self._insert_promo(item)
                    pass

                case _:
                    pass  # Allow other items to pass

        except Exception as e:
            raise DropItem(f"Error processing item: {e}")

        return item

    def process_unit_item(self, item: UnitItem, property_id: int):
        try:
            self.cur.execute("BEGIN;")
            floorplan_id = self._upsert_floorplan(item, property_id)
            unit_id = self._upsert_apartment_unit(item, property_id, floorplan_id)
            self._insert_price_history(item, unit_id)
            self.conn.commit()

        except Exception as e:
            self.logger.error(f"Transaction failed: {e}")
            self.conn.rollback()  # Roll back all changes if any step fails
            raise e

    def _upsert_property(self, item: PropertyItem, company_id: int) -> int:
        # Use a property URL or a combined City/Name as the ON CONFLICT target
        # TODO! Update primary key to something beyond the URL alone
        sql = """
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

        self.cur.execute(
            sql,
            {
                "company_id": company_id,
                "name": item.get("property_name"),
                "url": item.get("url"),
                "template": item.get("template_engine"),
                "address": item.get("address"),
                "city": item.get("city"),
                "state": item.get("state"),
                "postal_code": item.get("postal_code"),
            },
        )

        result = self.cur.fetchone()
        if not result:
            raise ValueError(
                f"Failed to upsert property with URL={item.get('property_url')}"
            )

        self.logger.info(f"Upserted property_id: {result[0]}")
        return result[0]

    def _upsert_floorplan(self, item: UnitItem, property_id: int) -> int:
        # TODO: Consider if DO UPDATE is needed here to update metadata
        # Check out this: https://stackoverflow.com/questions/34708509/how-to-use-returning-with-on-conflict-in-postgresql
        sql = """
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
        self.cur.execute(
            sql,
            {
                "prop_id": property_id,
                "plan_name": item.get("floorplan_name"),
                "bedrooms": item.get("num_bedrooms"),
                "bathrooms": item.get("num_bathrooms"),
                "square_footage": item.get("square_footage"),
            },
        )

        result = self.cur.fetchone()
        if not result:
            raise ValueError(
                f"Failed to retrieve floorplan_id for property_id={property_id} and plan_name={item.get('floorplan_name')}"
            )

        self.logger.info(f"Upserted floorplan_id: {result[0]}")
        return result[0]

    def _upsert_apartment_unit(
        self, item: UnitItem, property_id: int, floorplan_id: int
    ) -> int:
        sql = """
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
                ON CONFLICT (property_id, unit_number) DO NOTHING 
                RETURNING unit_id
            )
            SELECT unit_id FROM upsert
            UNION
                SELECT unit_id
                FROM apartment_units
                WHERE (
                    property_id = %(prop_id)s 
                    AND unit_number = %(unit_number)s
                );
        """
        self.cur.execute(
            sql,
            {
                "prop_id": property_id,
                "floorplan_id": floorplan_id,
                "unit_number": item.get("unit_number"),
                "floor_number": item.get("floor_number"),
                "building_name": item.get("building_name"),
                "is_on_top_floor": item.get("top_floor"),
            },
        )

        result = self.cur.fetchone()
        if not result:
            raise ValueError(
                f"Failed to retrieve unit_id for property_id={property_id} and unit_number={item['unit_number']}"
            )

        self.logger.info(f"Upserted unit_id: {result[0]}")
        return result[0]

    def _insert_price_history(self, item: UnitItem, unit_id: int) -> None:
        sql = """
            INSERT INTO price_history (
                scraped_at,
                unit_id,
                rent_usd,
                deposit_usd,
                min_lease_term_months,
                available_date
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        self.cur.execute(
            sql,
            (
                item.get("scraped_at"),
                unit_id,
                item.get("rent_usd"),
                item.get("deposit_usd"),
                item.get("min_lease_term_months"),
                item.get("available_date"),
            ),
        )

    def _insert_promo(self, item: PromoItem) -> int:
        # SQL logic, often using ON CONFLICT to retrieve the existing floorplan_id
        # and cache it, so the ApartmentUnitItem can use it later.
        raise NotImplementedError("Method not yet implemented.")

    def _get_property_id(self, url: str) -> int:
        # SQL logic to retrieve property_id based on a natural key
        sql_select = """
            SELECT property_id FROM properties
            WHERE url = %s;
        """
        self.cur.execute(sql_select, (url,))
        result = self.cur.fetchone()
        if not result:
            raise ValueError(f"Failed to retrieve property_id for URL={url}")
        return result[0]

    def _get_company_id(self, company_name: str) -> int:
        sql = """
            SELECT company_id FROM management_companies
            WHERE name = %s;
        """
        self.cur.execute(sql, (company_name,))
        result = self.cur.fetchone()
        if not result:
            raise ValueError(
                f"Failed to retrieve company_id for company_name={company_name}"
            )
        return result[0]
