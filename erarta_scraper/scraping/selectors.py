class CatalogLocators:
    @staticmethod
    def product_cards(page_index: int) -> str:
        return f"div#product_list_{page_index} > div.product-grid-item"


class ArtworkLocators:
    TITLE = "//h1[@class='title']"
    ARTIST = "//h2[@class='author']//a"
    PRICE_SECONDARY = "(//span[@class='price-value'])[2]"
    PRICE_PRIMARY = "(//span[@class='price-value'])"
    SIZE = "//div[@class='left-container-detail']//form[1]//div[3]//div[1]//p[1]"
    YEAR = "//div[@class='no-curl']//form[1]//div[4]//div[1]//p[1]"
    ART_TYPE = "//div[@class='left-container-detail']//form[2]//div[2]//div[1]//p[1]//a[1]"
    GENRE = "//div[@class='no-curl']//div[3]//div[1]//p[1]//a[1]"
    BAGUETTE = "//div[@class='left-container-detail']//div[6]//div[1]//p[1]//a[1]"
    TECHNIQUE = "//div[@class='no-curl']//div[@class='hidden-xs']//div[5]//div[1]//p[1]//a[1]"
