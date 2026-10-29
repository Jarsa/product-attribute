# Copyright 2019-2020 Camptocamp (<https://www.camptocamp.com>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html)
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    packaging_ids = fields.One2many(
        "product.packaging",
        "product_id",
        string="Product Packages",
        help="Gives the different ways to package the same product.",
    )
