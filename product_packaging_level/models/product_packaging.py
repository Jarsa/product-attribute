# Copyright 2019-2020 Camptocamp (<https://www.camptocamp.com>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html)
from collections import OrderedDict

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_round


class ProductPackaging(models.Model):
    _name = "product.packaging"
    _description = "Product Packaging"
    _order = "product_id, sequence, id"
    _check_company_auto = True

    name = fields.Char(
        string="Product Packaging",
        compute="_compute_name",
        store=True,
        readonly=False,
        required=True,
    )
    sequence = fields.Integer(
        default=1,
        compute="_compute_sequence",
        store=True,
        readonly=False,
        help="The first in the sequence is the default one.",
    )
    product_id = fields.Many2one(
        "product.product",
        check_company=True,
        required=True,
        ondelete="cascade",
    )
    qty = fields.Float(
        string="Contained Quantity",
        default=1.0,
        digits="Product Unit",
        help="Quantity of products contained in the packaging.",
    )
    barcode = fields.Char(
        copy=False,
        help="Barcode used for packaging identification.",
    )
    product_uom_id = fields.Many2one(
        "uom.uom", related="product_id.uom_id", readonly=True
    )
    company_id = fields.Many2one("res.company", index=True)
    package_type_id = fields.Many2one("stock.package.type")
    route_ids = fields.Many2many(
        "stock.route",
        "stock_route_packaging",
        "packaging_id",
        "route_id",
        string="Routes",
        domain=[("package_type_selectable", "=", True)],
    )
    packaging_level_id = fields.Many2one(
        "product.packaging.level",
        required=True,
        ondelete="restrict",
        default=lambda p: p.default_packaging_level_id(),
    )
    barcode_required_for_gtin = fields.Boolean(
        readonly=True, compute="_compute_barcode_required_for_gtin"
    )
    qty_per_level = fields.Char(
        compute="_compute_qty_per_level", string="Qty per package level"
    )
    name_policy = fields.Selection(related="packaging_level_id.name_policy")

    _positive_qty = models.Constraint(
        "CHECK(qty > 0)", "Contained Quantity should be positive."
    )
    _barcode_uniq = models.Constraint(
        "unique(barcode)", "A barcode can only be assigned to one packaging."
    )

    @api.constrains("barcode")
    def _check_barcode_uniqueness(self):
        domain = [("barcode", "in", [b for b in self.mapped("barcode") if b])]
        if self.env["product.product"].search(domain, order="id", limit=1):
            raise ValidationError(self.env._("A product already uses the barcode"))

    def _check_qty(self, product_qty, uom_id, rounding_method="HALF-UP"):
        self.ensure_one()
        default_uom = self.product_id.uom_id
        packaging_qty = default_uom._compute_quantity(self.qty, uom_id)
        if product_qty and packaging_qty:
            rounded_qty = (
                float_round(
                    product_qty / packaging_qty,
                    precision_rounding=1.0,
                    rounding_method=rounding_method,
                )
                * packaging_qty
            )
            return (
                rounded_qty
                if float_compare(
                    rounded_qty, product_qty, precision_rounding=default_uom.rounding
                )
                else product_qty
            )
        return product_qty

    def _find_suitable_product_packaging(self, product_qty, uom_id):
        packagings = self.sorted(lambda p: p.qty, reverse=True)
        for packaging in packagings:
            new_qty = packaging._check_qty(product_qty, uom_id)
            if new_qty == product_qty:
                return packaging
        return self.env["product.packaging"]

    def _compute_qty(self, qty, qty_uom=False):
        self.ensure_one()
        if qty_uom:
            qty = qty_uom._compute_quantity(qty, self.product_uom_id)
        return float_round(
            qty / self.qty, precision_rounding=self.product_uom_id.rounding
        )

    def default_packaging_level_id(self):
        return self.env["product.packaging.level"].search(
            [("is_default", "=", True)], limit=1
        )

    @api.constrains("packaging_level_id", "product_id")
    def _check_one_packaging_level_per_product(self):
        packages_name_by_level = self.filtered(
            lambda p: p.name_policy == "by_package_level"
        )
        for packaging in packages_name_by_level:
            product = packaging.product_id
            packaging_level_ids = [
                packaging.packaging_level_id.id
                for packaging in product.packaging_ids
                if not packaging.packaging_level_id.is_default
            ]
            if len(set(packaging_level_ids)) != len(packaging_level_ids):
                raise ValidationError(
                    self.env._(
                        "It is forbidden to have different packagings "
                        "with the same level for a given product (%(product)s).",
                        product=product.display_name,
                    )
                )

    @api.depends("packaging_level_id")
    def _compute_sequence(self):
        for packaging in self:
            packaging.sequence = packaging.packaging_level_id.sequence

    @api.depends("packaging_level_id", "packaging_level_id.has_gtin", "qty")
    def _compute_barcode_required_for_gtin(self):
        for packaging in self:
            packaging.barcode_required_for_gtin = packaging.packaging_level_id.has_gtin
            if not packaging.qty:
                packaging.barcode_required_for_gtin = False

    @api.depends(
        "product_id",
        "product_id.packaging_ids",
        "packaging_level_id",
        "packaging_level_id.code",
    )
    def _compute_qty_per_level(self):
        for packaging in self:
            mapping = packaging._get_qty_per_level_mapping()
            packaging.qty_per_level = packaging._format_qty_per_level(mapping)

    def _get_qty_per_level_mapping(self):
        """Retrieve qty for each packaging level.

        :return: mapping {level.code: qty}
        """
        smaller_product_packagings = self.product_id.packaging_ids.filtered(
            lambda p: p.id != self.id and self.qty > p.qty > 0.0
        )
        res = OrderedDict()
        for p_pack in smaller_product_packagings.sorted(lambda p: p.qty):
            res[p_pack.packaging_level_id.code] = p_pack.qty
        return res

    def _format_qty_per_level(self, qty_per_level_mapping, format_pattern=None):
        """Format given qty per level mapping as string."""
        qty_per_level = self._make_qty_per_level(
            qty_per_level_mapping, format_pattern=format_pattern
        )
        res = []
        for code, qty in qty_per_level:
            res.append(f"{qty} {code}")
        return "; ".join(res)

    def _make_qty_per_level(self, qty_per_level_mapping, format_pattern=None):
        """Prepare list of packaging qty by code."""
        res = []
        format_pattern = format_pattern or "{}{}"
        for code, qty in qty_per_level_mapping.items():
            new_qty = self.qty / qty
            if not new_qty.is_integer():
                new_qty_int = int(new_qty)
                new_qty_decimals = new_qty - new_qty_int
                new_qty = format_pattern.format(
                    new_qty_int, str(new_qty_decimals).lstrip("0")
                )
            res.append((code, new_qty))
        return res

    @api.onchange("package_type_id")
    def _onchange_package_type(self):
        package_type_level_id = self.package_type_id.packaging_level_id
        if package_type_level_id:
            self.packaging_level_id = package_type_level_id

    @api.depends(
        "package_type_id",
        "name_policy",
        "packaging_level_id",
    )
    def _compute_name(self):
        for rec in self:
            rec.name = rec._get_name_from_policy()

    @api.depends("product_id", "packaging_level_id", "name_policy")
    def _compute_display_name(self):
        res = super()._compute_display_name()
        for record in self:
            if record.product_id and record.packaging_level_id:
                record.display_name = record._get_name_from_policy(lang=self.env.lang)
        return res

    def _get_name_from_policy(self, lang=None):
        new_name = self.name
        if self.name_policy == "by_package_level":
            lang = lang or self.packaging_level_id.default_lang_id.code
            rec = self.with_context(lang=lang)
            new_name = rec.packaging_level_id.display_name
        elif self.name_policy == "by_package_type":
            new_name = self.package_type_id.name
        return new_name
