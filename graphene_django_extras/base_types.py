import binascii
import datetime

import graphene
from graphene.types.datetime import Date, DateTime, Time
from graphene.utils.str_converters import to_camel_case
from graphql.language import ast


def factory_type(operation, _type, *args, **kwargs):
    if operation == 'output':

        class GenericType(_type):
            class Meta:
                model = kwargs.get('model')
                name = kwargs.get('name') or to_camel_case(
                    '{}_Generic_Type'.format(kwargs.get('model').__name__)
                )
                only_fields = kwargs.get('only_fields')
                exclude_fields = kwargs.get('exclude_fields')
                include_fields = kwargs.get('include_fields')
                filter_fields = kwargs.get('filter_fields')
                filterset_class = kwargs.get('filterset_class')
                registry = kwargs.get('registry')
                skip_registry = kwargs.get('skip_registry')
                # fields = kwargs.get('fields')
                description = 'Auto generated Type for {} model'.format(
                    kwargs.get('model').__name__
                )

        return GenericType

    if operation == 'input':

        class GenericInputType(_type):
            class Meta:
                model = kwargs.get('model')
                name = kwargs.get('name') or to_camel_case(
                    '{}_{}_Generic_Type'.format(kwargs.get('model').__name__, args[0])
                )
                only_fields = kwargs.get('only_fields')
                exclude_fields = kwargs.get('exclude_fields')
                nested_fields = kwargs.get('nested_fields')
                registry = kwargs.get('registry')
                skip_registry = kwargs.get('skip_registry')
                input_for = args[0]
                description = 'Auto generated InputType for {} model'.format(
                    kwargs.get('model').__name__
                )

        return GenericInputType

    if operation == 'list':

        class GenericListType(_type):
            class Meta:
                model = kwargs.get('model')
                name = kwargs.get('name') or to_camel_case(
                    '{}_List_Type'.format(kwargs.get('model').__name__)
                )
                only_fields = kwargs.get('only_fields')
                exclude_fields = kwargs.get('exclude_fields')
                filter_fields = kwargs.get('filter_fields')
                filterset_class = kwargs.get('filterset_class')
                results_field_name = kwargs.get('results_field_name')
                pagination = kwargs.get('pagination')
                queryset = kwargs.get('queryset')
                registry = kwargs.get('registry')
                description = 'Auto generated list Type for {} model'.format(
                    kwargs.get('model').__name__
                )

        return GenericListType

    return None


class DjangoListObjectBase:
    def __init__(self, results, count, results_field_name='results'):
        self.results = results
        self.count = count
        self.results_field_name = results_field_name

    def to_dict(self):
        return {
            self.results_field_name: [e.to_dict() for e in self.results],
            'count': self.count,
        }


def resolver(attr_name, root, instance, info):
    if attr_name == 'app_label':
        return instance._meta.app_label
    if attr_name == 'id':
        return instance.id
    if attr_name == 'model_name':
        return instance._meta.model.__name__


class GenericForeignKeyType(graphene.ObjectType):
    app_label = graphene.String()
    id = graphene.ID()
    model_name = graphene.String()

    class Meta:
        description = " Auto generated Type for a model's GenericForeignKey field "
        default_resolver = resolver


class GenericForeignKeyInputType(graphene.InputObjectType):
    app_label = graphene.Argument(graphene.String, required=True)
    id = graphene.Argument(graphene.ID, required=True)
    model_name = graphene.Argument(graphene.String, required=True)

    class Meta:
        description = " Auto generated InputType for a model's GenericForeignKey field "


# ************************************************ #
# ************** CUSTOM BASE TYPES *************** #
# ************************************************ #
class Binary(graphene.Scalar):
    """
    BinaryArray is used to convert a Django BinaryField to the string form
    """

    @staticmethod
    def binary_to_string(value):
        return binascii.hexlify(value).decode('utf-8')

    serialize = binary_to_string
    parse_value = binary_to_string

    @classmethod
    def parse_literal(cls, node):
        if isinstance(node, ast.StringValue):
            return cls.binary_to_string(node.value)


class CustomDateFormat:
    def __init__(self, date):
        self.date_str = date


class CustomTime(Time):
    @staticmethod
    def serialize(time):
        if isinstance(time, CustomDateFormat):
            return time.date_str

        if isinstance(time, datetime.datetime):
            time = time.time()

        if not isinstance(time, datetime.time):
            raise TypeError(f'Received not compatible time "{time!r}"')
        return time.isoformat()


class CustomDate(Date):
    @staticmethod
    def serialize(date):
        if isinstance(date, CustomDateFormat):
            return date.date_str

        if isinstance(date, datetime.datetime):
            date = date.date()
        if not isinstance(date, datetime.date):
            raise TypeError(f'Received not compatible date "{date!r}"')
        return date.isoformat()


class CustomDateTime(DateTime):
    @staticmethod
    def serialize(dt):
        if isinstance(dt, CustomDateFormat):
            return dt.date_str

        if not isinstance(dt, (datetime.datetime, datetime.date)):
            raise TypeError(f'Received not compatible datetime "{dt!r}"')
        return dt.isoformat()
