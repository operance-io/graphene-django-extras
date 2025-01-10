from collections import OrderedDict

from django.db.models import QuerySet
from django.utils.functional import SimpleLazyObject
from graphene import ID, Argument, Boolean, Field, InputField, Int, List, ObjectType
from graphene.types.base import BaseOptions
from graphene.types.inputobjecttype import InputObjectType, InputObjectTypeContainer
from graphene.types.utils import yank_fields_from_attrs
from graphene.utils.deprecated import warn_deprecation
from graphene.utils.props import props
from graphene_django.types import ErrorType
from graphene_django.utils import (
    DJANGO_FILTER_INSTALLED,
    is_valid_django_model,
    maybe_queryset,
)

from .base_types import DjangoListObjectBase, factory_type
from .converter import construct_fields
from .fields import DjangoListField, DjangoListObjectField, DjangoObjectField
from .paginations.pagination import BaseDjangoGraphqlPagination
from .registry import Registry, get_global_registry
from .settings import graphql_api_settings
from .utils import get_Object_or_None, queryset_factory

__all__ = (
    'DjangoInputObjectType',
    'DjangoListObjectType',
    'DjangoObjectType',
    'DjangoSerializerType',
)


class DjangoObjectOptions(BaseOptions):
    fields = None
    input_fields = None
    interfaces = ()
    model = None
    queryset = None
    registry = None
    connection = None
    create_container = None
    results_field_name = None
    filter_fields = ()
    input_for = None
    filterset_class = None


class DjangoSerializerOptions(BaseOptions):
    model = None
    queryset = None
    serializer_class = None

    arguments = None
    fields = None
    input_fields = None
    input_field_name = None

    mutation_output = None
    output_field_name = None
    output_type = None
    output_list_type = None
    nested_fields = None
    interfaces = ()


class DjangoObjectType(ObjectType):
    @classmethod
    def __init_subclass_with_meta__(
        cls,
        model=None,
        registry=None,
        skip_registry=False,
        only_fields=(),
        exclude_fields=(),
        include_fields=(),
        filter_fields=None,
        interfaces=(),
        filterset_class=None,
        **options,
    ):
        assert is_valid_django_model(
            model
        ), f'You need to pass a valid Django Model in {cls.__name__}.Meta, received "{model}".'

        if not registry:
            registry = get_global_registry()

        assert isinstance(registry, Registry), (
            f'The attribute registry in {cls.__name__} needs to be an instance of '
            f'Registry, received "{registry}".'
        )

        if not DJANGO_FILTER_INSTALLED and (filter_fields or filterset_class):
            raise Exception(
                'Can only set filter_fields or filterset_class if Django-Filter is installed'
            )

        django_fields = yank_fields_from_attrs(
            construct_fields(
                model, registry, only_fields, include_fields, exclude_fields
            ),
            _as=Field,
        )

        _meta = DjangoObjectOptions(cls)
        _meta.model = model
        _meta.registry = registry
        _meta.filter_fields = filter_fields
        _meta.fields = django_fields
        _meta.filterset_class = filterset_class

        super().__init_subclass_with_meta__(
            _meta=_meta, interfaces=interfaces, **options
        )

        if not skip_registry:
            registry.register(cls)

    def resolve_id(self, info):
        return self.pk

    @classmethod
    def is_type_of(cls, root, info):
        if isinstance(root, SimpleLazyObject):
            root._setup()
            root = root._wrapped
        if isinstance(root, cls):
            return True
        if not is_valid_django_model(type(root)):
            raise Exception(f'Received incompatible instance "{root}".')
        return isinstance(root, cls._meta.model)

    @classmethod
    def get_queryset(cls, queryset, info):
        return queryset

    @classmethod
    def get_node(cls, info, id):
        try:
            return cls._meta.model.objects.get(pk=id)
        except cls._meta.model.DoesNotExist:
            return None


class DjangoInputObjectType(InputObjectType):
    @classmethod
    def __init_subclass_with_meta__(
        cls,
        model=None,
        container=None,
        registry=None,
        skip_registry=False,
        connection=None,
        use_connection=None,
        only_fields=(),
        exclude_fields=(),
        filter_fields=None,
        input_for='create',
        nested_fields=(),
        **options,
    ):
        assert is_valid_django_model(
            model
        ), f'You need to pass a valid Django Model in {cls.__name__}.Meta, received "{model}".'

        if not registry:
            registry = get_global_registry()

        assert isinstance(registry, Registry), (
            f'The attribute registry in {cls.__name__} needs to be an instance of '
            f'Registry, received "{registry}".'
        )

        assert (
            input_for.lower not in ('create', 'delete', 'update')
        ), f'You need to pass a valid input_for value in {cls.__name__}.Meta, received "{input_for}".'

        input_for = input_for.lower()

        if not DJANGO_FILTER_INSTALLED and filter_fields:
            raise Exception('Can only set filter_fields if Django-Filter is installed')

        django_input_fields = yank_fields_from_attrs(
            construct_fields(
                model,
                registry,
                only_fields,
                None,
                exclude_fields,
                input_for,
                nested_fields,
            ),
            _as=InputField,
            sort=False,
        )

        for base in reversed(cls.__mro__):
            django_input_fields.update(
                yank_fields_from_attrs(base.__dict__, _as=InputField)
            )

        if container is None:
            container = type(cls.__name__, (InputObjectTypeContainer, cls), {})

        _meta = DjangoObjectOptions(cls)
        _meta.by_polar = True
        _meta.model = model
        _meta.registry = registry
        _meta.filter_fields = filter_fields
        _meta.fields = django_input_fields
        _meta.input_fields = django_input_fields
        _meta.connection = connection
        _meta.input_for = input_for
        _meta.container = container

        super(InputObjectType, cls).__init_subclass_with_meta__(
            # container=container,
            _meta=_meta,
            **options,
        )

        if not skip_registry:
            registry.register(cls, for_input=input_for)

    @classmethod
    def get_type(cls):
        """
        This function is called when the unmounted type (InputObjectType instance)
        is mounted (as a Field, InputField or Argument)
        """
        return cls


class DjangoListObjectType(ObjectType):
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(
        cls,
        model=None,
        registry=None,
        results_field_name=None,
        pagination=None,
        only_fields=(),
        exclude_fields=(),
        filter_fields=None,
        queryset=None,
        filterset_class=None,
        **options,
    ):
        if not is_valid_django_model(model):
            raise TypeError(
                f'You need to pass a valid Django Model in {cls.__name__}.Meta, '
                f'received "{model}".'
            )

        if not registry:
            registry = get_global_registry()

        if not DJANGO_FILTER_INSTALLED and filter_fields:
            raise Exception('Can only set filter_fields if Django-Filter is installed')

        if not isinstance(queryset, QuerySet) and queryset is not None:
            raise TypeError(
                f'The attribute queryset in {cls.__name__} needs to be an instance of '
                f'Django model queryset, received "{queryset}".'
            )

        results_field_name = results_field_name or 'results'

        base_type = get_global_registry().get_type_for_model(model)

        if not base_type:
            factory_kwargs = {
                'model': model,
                'only_fields': only_fields,
                'exclude_fields': exclude_fields,
                'filter_fields': filter_fields,
                'filterset_class': filterset_class,
                'pagination': pagination,
                'queryset': queryset,
                'registry': registry,
                'skip_registry': False,
            }
            base_type = factory_type('output', DjangoObjectType, **factory_kwargs)

        filter_fields = filter_fields or base_type._meta.filter_fields

        if pagination:
            result_container = pagination.get_pagination_field(base_type)
        else:
            global_paginator = graphql_api_settings.DEFAULT_PAGINATION_CLASS
            if global_paginator:
                assert issubclass(
                    global_paginator, BaseDjangoGraphqlPagination
                ), f'You need to pass a valid DjangoGraphqlPagination class in {cls.__name__}.Meta, received "{global_paginator}".'

                global_paginator = global_paginator()
                result_container = global_paginator.get_pagination_field(base_type)
            else:
                result_container = DjangoListField(base_type)

        _meta = DjangoObjectOptions(cls)
        _meta.model = model
        _meta.registry = registry
        _meta.queryset = queryset
        _meta.baseType = base_type
        _meta.results_field_name = results_field_name
        _meta.filter_fields = filter_fields
        _meta.exclude_fields = exclude_fields
        _meta.only_fields = only_fields
        _meta.filterset_class = filterset_class
        _meta.fields = OrderedDict(
            [
                (results_field_name, result_container),
                (
                    'count',
                    Field(
                        Int,
                        name='totalCount',
                        description='Total count of matches elements',
                    ),
                ),
            ]
        )

        super().__init_subclass_with_meta__(_meta=_meta, **options)

    @classmethod
    def RetrieveField(cls, *args, **kwargs):  # noqa: N802
        return DjangoObjectField(cls._meta.baseType, **kwargs)

    @classmethod
    def BaseType(cls):  # noqa: N802
        return cls._meta.baseType


class DjangoSerializerType(ObjectType):
    """
    DjangoSerializerType definition
    """

    ok = Boolean(description='Boolean field that return mutation result request.')
    errors = List(ErrorType, description='Errors list for the field')

    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(
        cls,
        serializer_class=None,
        queryset=None,
        only_fields=(),
        include_fields=(),
        exclude_fields=(),
        pagination=None,
        input_field_name=None,
        output_field_name=None,
        results_field_name=None,
        nested_fields=(),
        filter_fields=None,
        description='',
        filterset_class=None,
        **options,
    ):
        if not serializer_class:
            raise Exception('serializer_class is required on all ModelSerializerType')

        model = serializer_class.Meta.model

        description = description or f'ModelSerializerType for {model.__name__} model'

        input_field_name = input_field_name or f'new_{model._meta.model_name}'
        output_field_name = output_field_name or model._meta.model_name

        input_class = getattr(cls, 'Arguments', None)
        if not input_class:
            input_class = getattr(cls, 'Input', None)
            if input_class:
                warn_deprecation(
                    f'Please use {cls.__name__}.Arguments instead of {cls.__name__}.Input.'
                    'Input is now only used in ClientMutationID.\nRead more: '
                    'https://github.com/graphql-python/graphene/blob/2.0/UPGRADE-v2.0.md#mutation-input'
                )
        arguments = props(input_class) if input_class else {}

        registry = get_global_registry()

        factory_kwargs = {
            'model': model,
            'only_fields': only_fields,
            'include_fields': include_fields,
            'exclude_fields': exclude_fields,
            'filter_fields': filter_fields,
            'pagination': pagination,
            'queryset': queryset,
            'nested_fields': nested_fields,
            'registry': registry,
            'skip_registry': False,
            'filterset_class': filterset_class,
            'results_field_name': results_field_name,
        }

        output_type = registry.get_type_for_model(model)

        if not output_type:
            output_type = factory_type('output', DjangoObjectType, **factory_kwargs)

        output_list_type = factory_type('list', DjangoListObjectType, **factory_kwargs)

        django_fields = OrderedDict({output_field_name: Field(output_type)})

        global_arguments = {}
        for operation in ('create', 'delete', 'update'):
            global_arguments.update({operation: OrderedDict()})

            if operation != 'delete':
                input_type = registry.get_type_for_model(model, for_input=operation)

                if not input_type:
                    # factory_kwargs.update({'skip_registry': True})
                    input_type = factory_type(
                        'input', DjangoInputObjectType, operation, **factory_kwargs
                    )

                global_arguments[operation].update(
                    {input_field_name: Argument(input_type, required=True)}
                )
            else:
                global_arguments[operation].update(
                    {
                        'id': Argument(
                            ID,
                            required=True,
                            description='Django object unique identification field',
                        )
                    }
                )
            global_arguments[operation].update(arguments)

        _meta = DjangoSerializerOptions(cls)
        _meta.mutation_output = cls
        _meta.arguments = global_arguments
        _meta.fields = django_fields
        _meta.output_type = output_type
        _meta.output_list_type = output_list_type
        _meta.model = model
        _meta.registry = registry
        _meta.queryset = queryset or model._default_manager
        _meta.serializer_class = serializer_class
        _meta.input_field_name = input_field_name
        _meta.output_field_name = output_field_name
        _meta.nested_fields = nested_fields

        super().__init_subclass_with_meta__(
            _meta=_meta, description=description, **options
        )

    @classmethod
    def list_object_type(cls):
        return cls._meta.output_list_type

    @classmethod
    def object_type(cls):
        return cls._meta.output_type

    @classmethod
    def get_errors(cls, errors):
        errors_dict = {cls._meta.output_field_name: None, 'ok': False, 'errors': errors}

        return cls(**errors_dict)

    @classmethod
    def perform_mutate(cls, obj, info):
        resp = {cls._meta.output_field_name: obj, 'ok': True, 'errors': None}

        return cls(**resp)

    @classmethod
    def get_serializer_kwargs(cls, root, info, **kwargs):
        return {}

    @classmethod
    def manage_nested_fields(cls, data, root, info):
        nested_objs = {}
        if cls._meta.nested_fields and isinstance(cls._meta.nested_fields, dict):
            for field in cls._meta.nested_fields:
                sub_data = data.pop(field, None)
                if sub_data:
                    serialized_data = cls._meta.nested_fields[field](
                        data=sub_data, many=isinstance(sub_data, list)
                    )
                    ok, result = cls.save(serialized_data, root, info)
                    if not ok:
                        return cls.get_errors(result)
                    if isinstance(sub_data, list):
                        nested_objs.update({field: result})
                    else:
                        data.update({field: result.id})
        return nested_objs

    @classmethod
    def create(cls, root, info, **kwargs):
        data = kwargs.get(cls._meta.input_field_name)
        request_type = info.context.META.get('CONTENT_TYPE', '')
        if 'multipart/form-data' in request_type:
            data.update(dict(info.context.FILES.items()))

        nested_objs = cls.manage_nested_fields(data, root, info)
        serializer = cls._meta.serializer_class(
            data=data, **cls.get_serializer_kwargs(root, info, **kwargs)
        )

        ok, obj = cls.save(serializer, root, info)
        if not ok:
            return cls.get_errors(obj)
        if nested_objs:
            [getattr(obj, field).add(*objs) for field, objs in nested_objs.items()]
        return cls.perform_mutate(obj, info)

    @classmethod
    def delete(cls, root, info, **kwargs):
        pk = kwargs.get('id')

        old_obj = get_Object_or_None(cls._meta.model, pk=pk)
        if old_obj:
            old_obj.delete()
            old_obj.id = pk
            return cls.perform_mutate(old_obj, info)
        return cls.get_errors(
            [
                ErrorType(
                    field='id',
                    messages=[
                        f'A {cls._meta.model.__name__} obj with id {pk} do not exist'
                    ],
                )
            ]
        )

    @classmethod
    def update(cls, root, info, **kwargs):
        data = kwargs.get(cls._meta.input_field_name)
        request_type = info.context.META.get('CONTENT_TYPE', '')
        if 'multipart/form-data' in request_type:
            data.update(dict(info.context.FILES.items()))

        pk = data.pop('id')
        old_obj = get_Object_or_None(cls._meta.model, pk=pk)
        if old_obj:
            nested_objs = cls.manage_nested_fields(data, root, info)
            serializer = cls._meta.serializer_class(
                old_obj,
                data=data,
                partial=True,
                **cls.get_serializer_kwargs(root, info, **kwargs),
            )

            ok, obj = cls.save(serializer, root, info)
            if not ok:
                return cls.get_errors(obj)
            if nested_objs:
                [getattr(obj, field).add(*objs) for field, objs in nested_objs.items()]
            return cls.perform_mutate(obj, info)
        return cls.get_errors(
            [
                ErrorType(
                    field='id',
                    messages=[
                        f'A {cls._meta.model.__name__} obj with id: {pk} do not exist'
                    ],
                )
            ]
        )

    @classmethod
    def save(cls, serialized_obj, root, info, **kwargs):
        if serialized_obj.is_valid():
            obj = serialized_obj.save()
            return True, obj

        errors = [
            ErrorType(field=key, messages=value)
            for key, value in serialized_obj.errors.items()
        ]
        return False, errors

    @classmethod
    def retrieve(cls, manager, root, info, **kwargs):
        pk = kwargs.pop('id', None)

        try:
            return manager.get_queryset().get(pk=pk)
        except manager.model.DoesNotExist:
            return None

    @classmethod
    def list(cls, manager, filterset_class, filtering_args, root, info, **kwargs):
        qs = queryset_factory(cls._meta.queryset or manager, root, info, **kwargs)

        filter_kwargs = {k: v for k, v in kwargs.items() if k in filtering_args}

        qs = filterset_class(data=filter_kwargs, queryset=qs).qs
        count = qs.count()

        return DjangoListObjectBase(
            count=count,
            results=maybe_queryset(qs),
            results_field_name=cls.list_object_type()._meta.results_field_name,
        )

    @classmethod
    def RetrieveField(cls, *args, **kwargs):  # noqa: N802
        return DjangoObjectField(cls._meta.output_type, resolver=cls.retrieve, **kwargs)

    @classmethod
    def ListField(cls, *args, **kwargs):  # noqa: N802
        return DjangoListObjectField(
            cls._meta.output_list_type, resolver=cls.list, **kwargs
        )

    @classmethod
    def CreateField(cls, *args, **kwargs):  # noqa: N802
        return Field(
            cls._meta.mutation_output,
            args=cls._meta.arguments['create'],
            resolver=cls.create,
            **kwargs,
        )

    @classmethod
    def DeleteField(cls, *args, **kwargs):  # noqa: N802
        return Field(
            cls._meta.mutation_output,
            args=cls._meta.arguments['delete'],
            resolver=cls.delete,
            **kwargs,
        )

    @classmethod
    def UpdateField(cls, *args, **kwargs):  # noqa: N802
        return Field(
            cls._meta.mutation_output,
            args=cls._meta.arguments['update'],
            resolver=cls.update,
            **kwargs,
        )

    @classmethod
    def QueryFields(cls, *args, **kwargs):  # noqa: N802
        retrieve_field = cls.RetrieveField(*args, **kwargs)
        list_field = cls.ListField(*args, **kwargs)

        return retrieve_field, list_field

    @classmethod
    def MutationFields(cls, *args, **kwargs):  # noqa: N802
        create_field = cls.CreateField(*args, **kwargs)
        delete_field = cls.DeleteField(*args, **kwargs)
        update_field = cls.UpdateField(*args, **kwargs)

        return create_field, delete_field, update_field
