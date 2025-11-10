# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class ApartmentListingItem(scrapy.Item):
    building_id = scrapy.Field()
    unit_number = scrapy.Field()
    floorplan_name = scrapy.Field()
    floorplan_id = scrapy.Field()
    num_bedrooms = scrapy.Field()
    floor_area = scrapy.Field()
    rent = scrapy.Field()
    deposit = scrapy.Field()
    date_available = scrapy.Field()
    lease_term = scrapy.Field()