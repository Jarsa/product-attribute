# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    product_packaging_id = fields.Many2one(
        comodel_name="product.packaging",
        string="Packaging",
        compute="_compute_product_packaging_id",
        store=True,
        readonly=False,
        precompute=True,
        domain="[('sales', '=', True), ('product_id', '=', product_id)]",
        check_company=True,
    )
    product_packaging_qty = fields.Float(
        string="Packaging Quantity",
        compute="_compute_product_packaging_qty",
        store=True,
        readonly=False,
        precompute=True,
    )

    def _can_be_sold_error_condition(self):
        self.ensure_one()
        return self.product_packaging_id and not self.product_packaging_id.sales

    @api.constrains("product_packaging_id")
    def _check_product_packaging_can_be_sold(self):
        for line in self:
            if line._can_be_sold_error_condition():
                raise ValidationError(
                    self.env._(
                        "Packaging %(packaging)s on product %(product)s must be"
                        " set as 'Sales' in order to be used on a sale order.",
                        packaging=line.product_packaging_id.name,
                        product=line.product_id.name,
                    )
                )

    @api.depends("product_id", "product_uom_qty", "product_uom_id")
    def _compute_product_packaging_id(self):
        for line in self:
            if line.product_packaging_id.product_id != line.product_id:
                line.product_packaging_id = False
            if line.product_id and line.product_uom_qty and line.product_uom_id:
                suggested_packaging = line.product_id.packaging_ids.filtered(
                    lambda p, line=line: p.sales
                    and (p.product_id.company_id <= p.company_id <= line.company_id)
                )._find_suitable_product_packaging(
                    line.product_uom_qty, line.product_uom_id
                )
                line.product_packaging_id = (
                    suggested_packaging or line.product_packaging_id
                )
            if line.product_packaging_id and not line.product_packaging_id.sales:
                line.product_packaging_id = False

    @api.depends("product_packaging_id", "product_uom_id", "product_uom_qty")
    def _compute_product_packaging_qty(self):
        self.product_packaging_qty = 0
        for line in self:
            if not line.product_packaging_id:
                continue
            line.product_packaging_qty = line.product_packaging_id._compute_qty(
                line.product_uom_qty, line.product_uom_id
            )

    @api.depends("display_type", "product_id", "product_packaging_qty")
    def _compute_product_uom_qty(self):
        super()._compute_product_uom_qty()
        for line in self:
            if line.display_type or not line.product_packaging_id:
                continue
            packaging_uom = line.product_packaging_id.product_uom_id
            qty_per_packaging = line.product_packaging_id.qty
            product_uom_qty = packaging_uom._compute_quantity(
                line.product_packaging_qty * qty_per_packaging, line.product_uom_id
            )
            if (
                float_compare(
                    product_uom_qty,
                    line.product_uom_qty,
                    precision_rounding=line.product_uom_id.rounding,
                )
                != 0
            ):
                line.product_uom_qty = product_uom_qty

    @api.onchange("product_packaging_id")
    def _onchange_product_packaging_id(self):
        if self.product_packaging_id and self.product_uom_qty:
            newqty = self.product_packaging_id._check_qty(
                self.product_uom_qty, self.product_uom_id, "UP"
            )
            if (
                float_compare(
                    newqty,
                    self.product_uom_qty,
                    precision_rounding=self.product_uom_id.rounding,
                )
                != 0
            ):
                return {
                    "warning": {
                        "title": self.env._("Warning"),
                        "message": self.env._(
                            "This product is packaged by %(pack_size).2f %(pack_name)s. "
                            "You should sell %(quantity).2f %(unit)s.",
                            pack_size=self.product_packaging_id.qty,
                            pack_name=self.product_id.uom_id.name,
                            quantity=newqty,
                            unit=self.product_uom_id.name,
                        ),
                    },
                }

    def write(self, values):
        result = super().write(values)
        if (
            "product_uom_qty" in values
            and "product_packaging_qty" in values
            and "product_packaging_id" not in values
        ):
            self.env.remove_to_compute(self._fields["product_packaging_id"], self)
        return result
