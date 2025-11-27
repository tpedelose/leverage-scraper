# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

from scrapy import Item, Field


class PropertyItem(Item):
    # Metadata
    scraped_at = Field()
    template_engine = Field()
    company_name = Field()
    # company_url = Field()

    # Identifiers
    property_name = Field()
    url = Field()

    # Location
    address = Field()
    city = Field()
    state = Field()
    postal_code = Field()


class UnitItem(Item):
    # Metadata
    scraped_at = Field()
    property_url = Field()

    # Price info
    rent_usd = Field()
    deposit_usd = Field()
    admin_fee = Field()
    application_fee = Field()

    # Availability
    available_date = Field()
    is_available = Field()
    min_lease_term_months = Field()

    # Location
    building_name = Field()
    floor_number = Field()
    top_floor = Field()

    # Floor Plan
    floorplan_name = Field()
    floorplan_id = Field()
    num_bedrooms = Field()
    num_bathrooms = Field()
    square_footage = Field()

    # Identifiers
    unit_number = Field()


class PromoItem(Item):
    # Metadata
    scraped_at = Field()

    # Data
    text = Field()
    ext_floorplan_id = Field()
    has_available_units = Field()
