"""Whitelisted server-side register filters; applied before totals and pagination."""
import json
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, func, case
from app.modules.db.models.lead_opt_order import LeadOptOrder as Order
from app.modules.db.models.lead_opt_order import LeadOptOrderLine as Line
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.opt_unit import OptUnit
from app.modules.db.models.user import User
from app.shared.exceptions import ValidationError

NUMERIC = {'volume', 'due', 'paid', 'debt', 'ben', 'margin', 'plan', 'returned'}
TEXT = {'client', 'manager', 'buyer', 'supplier', 'inn', 'period', 'category', 'comment', 'okved'}
KEYS = NUMERIC | TEXT


def parse_filters(raw):
    try:
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict) or len(data) > len(KEYS):
            raise ValueError()
        result = {}
        for key, value in data.items():
            if key not in KEYS:
                raise ValueError()
            if key in TEXT:
                if not isinstance(value, str) or len(value) > 160:
                    raise ValueError()
                if value.strip(): result[key] = value.strip()
            else:
                if not isinstance(value, dict) or set(value) - {'min', 'max'}:
                    raise ValueError()
                bounds = {}
                for bound, number in value.items():
                    if number is None or number == '': continue
                    n = Decimal(str(number))
                    if not n.is_finite() or abs(n) > Decimal('1e18'):
                        raise ValueError()
                    bounds[bound] = n
                if 'min' in bounds and 'max' in bounds and bounds['min'] > bounds['max']:
                    raise ValueError()
                if bounds: result[key] = bounds
        return result
    except (ValueError, TypeError, InvalidOperation):
        raise ValidationError(message='Некорректный фильтр таблицы')


def expressions():
    def aggregate(value):
        return select(value).where(Line.order_id == Order.id).correlate(Order).scalar_subquery()
    ben = aggregate(case((func.count(Line.id) == func.count(Line.beneficiary_rate_percent),
        func.sum(func.round(Line.amount * Line.beneficiary_rate_percent / 100, 0))), else_=None))
    returned = func.coalesce(aggregate(func.sum(Line.beneficiary_paid_amount)), 0)
    manager = select(User.full_name).where(User.id == ContactGroupAssignment.owner_user_id).correlate(ContactGroupAssignment).scalar_subquery()
    category = (select(func.string_agg(OptUnit.category_code, ' ')).select_from(Line)
        .outerjoin(OptUnit, OptUnit.inn == Line.supplier_inn)
        .where(Line.order_id == Order.id).correlate(Order).scalar_subquery())
    return {'client': func.coalesce(Contact.full_name, Order.buyer_name),
        'manager': manager, 'buyer': Order.buyer_name, 'inn': Order.buyer_inn,
        'period': Order.period_code, 'okved': Order.buyer_okved,
        'supplier': aggregate(func.string_agg(func.coalesce(Line.supplier_name, Line.supplier_inn), ' ')),
        'category': category, 'comment': aggregate(func.string_agg(Line.comment, ' ')),
        'volume': Order.total_volume, 'due': Order.commission_due, 'paid': Order.amount_paid,
        'debt': Order.commission_due - Order.amount_paid, 'ben': ben,
        'margin': Order.amount_paid - ben, 'plan': Order.commission_due - ben, 'returned': returned}


def apply_register_query(query, filters, sort_key, descending):
    fields = expressions()
    for key, value in parse_filters(filters).items():
        field = fields[key]
        if key in TEXT:
            query = query.where(field.icontains(value, autoescape=True))
        else:
            if 'min' in value: query = query.where(field >= value['min'])
            if 'max' in value: query = query.where(field <= value['max'])
    if sort_key is not None and sort_key not in fields:
        raise ValidationError(message='Неизвестная колонка сортировки')
    field = fields.get(sort_key, Order.period_code)
    ordering = (field.desc() if descending else field.asc()).nulls_last()
    return query, ordering
