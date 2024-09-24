# example function
def get_recommended_products(customer_product_description):
    print("Running: get_recommended_products", customer_product_description)

    return 'Product name: Green Board, Product Link: https://assistor.online/green, Product Image: https://fastly.picsum.photos/id/7/200/300.jpg?hmac=_vgE8dZdzp3B8T1C9VrGrIMBkDOkFYbJNWqzJD47xNg'


TOOL_MAP = {
    "get_recommended_products": get_recommended_products,
    # ... other functions ...
}
