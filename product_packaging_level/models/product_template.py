# Copyright 2019-2020 Camptocamp (<https://www.camptocamp.com>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html)
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    packaging_ids = fields.One2many(
        "product.packaging",
        string="Product Packages",
        compute="_compute_packaging_ids",
        inverse="_inverse_packaging_ids",
        help="Gives the different ways to package the same product.",
    )

    @api.depends("product_variant_ids", "product_variant_ids.packaging_ids")
    def _compute_packaging_ids(self):
        for p in self:
            if len(p.product_variant_ids) == 1:
                p.packaging_ids = p.product_variant_ids.packaging_ids
            else:
                p.packaging_ids = False

    def _inverse_packaging_ids(self):
        for p in self:
            if len(p.product_variant_ids) == 1:
                p.product_variant_ids.packaging_ids = p.packaging_ids

    def _get_related_fields_variant_template(self):
        res = super()._get_related_fields_variant_template()
        if "packaging_ids" not in res:
            res.append("packaging_ids")
        return res
