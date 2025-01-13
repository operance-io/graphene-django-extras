from __future__ import annotations

import operator
from functools import partial
from typing import TYPE_CHECKING, Callable, Iterable

import graphene
from django.db.models.base import Model
from graphene import ID, Argument, Field, List
from graphene.types.structures import NonNull, Structure
from graphene_django.fields import DjangoListField as DjangoListFieldBase
from graphene_django.filter.utils import get_filtering_args_from_filterset
from graphene_django.utils import (
    DJANGO_FILTER_INSTALLED,
    is_valid_django_model,
    maybe_queryset,
)

from graphene_django_extras.filters.filter import get_filterset_class
from graphene_django_extras.settings import graphql_api_settings

from .base_types import DjangoListObjectBase
from .paginations.pagination import BaseDjangoGraphqlPagination
from .utils import find_field, get_extra_filters, get_related_fields, queryset_factory

if TYPE_CHECKING:
    from django.db.models import Manager, Model, QuerySet
    from django_filters import FilterSet


# *********************************************** #
# *********** FIELD FOR SINGLE OBJECT *********** #
# *********************************************** #
class DjangoObjectField(Field):
    def __init__(self, _type, *args, **kwargs):
        kwargs['id'] = ID(
            required=True, description='Django object unique identification field'
        )

        super().__init__(_type, *args, **kwargs)

    @property
    def model(self):
        return self.type._meta.node._meta.model

    @staticmethod
    def object_resolver(
        manager, root: graphene.ObjectType | None, info: graphene.ResolveInfo, **kwargs
    ):
        item_id = kwargs.pop('id', None)

        try:
            return manager.get_queryset().get(pk=item_id)
        except manager.model.DoesNotExist:
            return None

    def wrap_resolve(self, parent_resolver: Callable) -> partial[Model | None]:
        if graphql_api_settings.DJANGO_OBJECT_FIELD_RESOLVER:
            return partial(
                graphql_api_settings.DJANGO_OBJECT_FIELD_RESOLVER,
                self.type._meta.model._default_manager,
            )
        return partial(self.object_resolver, self.type._meta.model._default_manager)


# *********************************************** #
# *************** FIELDS FOR LIST *************** #
# *********************************************** #
class DjangoListField(DjangoListFieldBase):
    def __init__(self, _type, *args, **kwargs):
        if isinstance(_type, NonNull):
            _type = _type.of_type

        super(DjangoListFieldBase, self).__init__(List(NonNull(_type)), *args, **kwargs)

    def wrap_resolve(self, parent_resolver):
        resolver = self.resolver or parent_resolver
        _type = self.type
        if isinstance(_type, NonNull):
            _type = _type.of_type
        django_object_type = _type.of_type.of_type
        if graphql_api_settings.DJANGO_LIST_FIELD_RESOLVER:
            return partial(
                graphql_api_settings.DJANGO_LIST_FIELD_RESOLVER,
                django_object_type,
                resolver,
                self.get_manager(),
            )
        return partial(
            self.list_resolver,
            django_object_type,
            resolver,
            self.get_manager(),
        )


class DjangoFilterListField(Field):
    def __init__(
        self,
        _type,
        fields=None,
        extra_filter_meta=None,
        filterset_class=None,
        *args,
        **kwargs,
    ):
        if DJANGO_FILTER_INSTALLED:
            _fields = _type._meta.filter_fields
            _model = _type._meta.model

            self.fields = fields or _fields
            meta = {'model': _model, 'fields': self.fields}
            if extra_filter_meta:
                meta.update(extra_filter_meta)
            filterset_class = filterset_class or _type._meta.filterset_class
            self.filterset_class = get_filterset_class(filterset_class, **meta)
            self.filtering_args = get_filtering_args_from_filterset(
                self.filterset_class, _type
            )
            kwargs.setdefault('args', {})
            kwargs['args'].update(self.filtering_args)

            if 'id' not in kwargs['args']:
                self.filtering_args.update(
                    {
                        'id': Argument(
                            ID, description='Django object unique identification field'
                        )
                    }
                )
                kwargs['args'].update(
                    {
                        'id': Argument(
                            ID, description='Django object unique identification field'
                        )
                    }
                )

        if not kwargs.get('description'):
            kwargs['description'] = f'{_type._meta.model.__name__} list'

        super().__init__(List(_type), *args, **kwargs)

    @property
    def model(self):
        return self.type.of_type._meta.node._meta.model

    @staticmethod
    def list_resolver(
        manager: Manager,
        filterset_class: type[FilterSet],
        filtering_args: Iterable,
        root: graphene.ObjectType | None,
        info: graphene.ResolveInfo,
        **kwargs,
    ) -> QuerySet | Iterable:
        queryset = None
        field = None

        if root and is_valid_django_model(root._meta.model):
            available_related_fields = get_related_fields(root._meta.model)
            field = find_field(info.field_nodes[0], available_related_fields)
        filter_kwargs = {k: v for k, v in kwargs.items() if k in filtering_args}

        if field is not None:
            try:
                if filter_kwargs:
                    queryset = operator.attrgetter(
                        '{}.filter'.format(
                            getattr(field, 'related_name', None) or field.name
                        )
                    )(root)(**filter_kwargs)
                else:
                    queryset = operator.attrgetter(
                        '{}.all'.format(
                            getattr(field, 'related_name', None) or field.name
                        )
                    )(root)()
            except AttributeError:
                queryset = None

        if queryset is None:
            queryset = queryset_factory(manager, root, info, **kwargs)
            queryset = filterset_class(
                data=filter_kwargs, queryset=queryset, request=info.context
            ).qs

            if root and is_valid_django_model(root._meta.model):
                extra_filters = get_extra_filters(root, manager.model)
                queryset = queryset.filter(**extra_filters)

        return maybe_queryset(queryset)

    def wrap_resolve(self, parent_resolver: Callable) -> partial[QuerySet | Iterable]:
        current_type = self.type
        while isinstance(current_type, Structure):
            current_type = current_type.of_type
        if graphql_api_settings.DJANGO_FILTER_LIST_FIELD_RESOLVER:
            return partial(
                graphql_api_settings.DJANGO_FILTER_LIST_FIELD_RESOLVER,
                current_type._meta.model._default_manager,
                self.filterset_class,
                self.filtering_args,
            )
        return partial(
            self.list_resolver,
            current_type._meta.model._default_manager,
            self.filterset_class,
            self.filtering_args,
        )


class DjangoFilterPaginateListField(Field):
    def __init__(
        self,
        _type,
        pagination=None,
        fields=None,
        extra_filter_meta=None,
        filterset_class=None,
        *args,
        **kwargs,
    ):
        _fields = _type._meta.filter_fields
        _model = _type._meta.model

        self.fields = fields or _fields
        meta = {'model': _model, 'fields': self.fields}
        if extra_filter_meta:
            meta.update(extra_filter_meta)

        filterset_class = filterset_class or _type._meta.filterset_class
        self.filterset_class = get_filterset_class(filterset_class, **meta)
        self.filtering_args = get_filtering_args_from_filterset(
            self.filterset_class, _type
        )
        kwargs.setdefault('args', {})
        kwargs['args'].update(self.filtering_args)

        if 'id' not in kwargs['args']:
            self.filtering_args.update(
                {
                    'id': Argument(
                        ID, description='Django object unique identification field'
                    )
                }
            )
            kwargs['args'].update(
                {
                    'id': Argument(
                        ID, description='Django object unique identification field'
                    )
                }
            )

        pagination = pagination or graphql_api_settings.DEFAULT_PAGINATION_CLASS()

        if pagination is not None:
            if not isinstance(pagination, BaseDjangoGraphqlPagination):
                raise TypeError(
                    'You need to pass a valid DjangoGraphqlPagination in '
                    f'DjangoFilterPaginateListField, received "{pagination}".'
                )

            pagination_kwargs = pagination.to_graphql_fields()

            self.pagination = pagination
            kwargs.update(**pagination_kwargs)

        if not kwargs.get('description'):
            kwargs['description'] = f'{_type._meta.model.__name__} list'

        super().__init__(List(NonNull(_type)), *args, **kwargs)

    @property
    def model(self):
        return self.type.of_type._meta.node._meta.model

    def get_queryset(self, manager, root, info, **kwargs):
        return queryset_factory(manager, root, info, **kwargs)

    def list_resolver(
        self,
        manager: Manager,
        filterset_class: type[FilterSet],
        filtering_args: Iterable,
        root: graphene.ObjectType | None,
        info: graphene.ResolveInfo,
        **kwargs,
    ) -> DjangoListObjectBase:
        filter_kwargs = {k: v for k, v in kwargs.items() if k in filtering_args}
        queryset = self.get_queryset(manager, root, info, **kwargs)
        queryset = filterset_class(
            data=filter_kwargs, queryset=queryset, request=info.context
        ).qs

        if root and is_valid_django_model(root._meta.model):
            extra_filters = get_extra_filters(root, manager.model)
            queryset = queryset.filter(**extra_filters)

        if getattr(self, 'pagination', None):
            queryset = self.pagination.paginate_queryset(queryset, **kwargs)

        return maybe_queryset(queryset)

    def wrap_resolve(self, parent_resolver: Callable) -> partial[DjangoListObjectBase]:
        current_type = self.type
        while isinstance(current_type, Structure):
            current_type = current_type.of_type
        if graphql_api_settings.DJANGO_FILTER_PAGINATE_LIST_FIELD_RESOLVER:
            return partial(
                graphql_api_settings.DJANGO_FILTER_PAGINATE_LIST_FIELD_RESOLVER,
                current_type._meta.model._default_manager,
                getattr(self, 'pagination', None),
                self.filterset_class,
                self.filtering_args,
            )
        return partial(
            self.list_resolver,
            current_type._meta.model._default_manager,
            self.filterset_class,
            self.filtering_args,
        )


class DjangoListObjectField(Field):
    def __init__(
        self,
        _type,
        fields=None,
        extra_filter_meta=None,
        filterset_class=None,
        *args,
        **kwargs,
    ):
        if DJANGO_FILTER_INSTALLED:
            _fields = _type._meta.filter_fields
            _model = _type._meta.model

            self.fields = fields or _fields

            meta = {'model': _model, 'fields': self.fields}
            if extra_filter_meta:
                meta.update(extra_filter_meta)

            filterset_class = filterset_class or _type._meta.filterset_class
            self.filterset_class = get_filterset_class(filterset_class, **meta)
            self.filtering_args = get_filtering_args_from_filterset(
                self.filterset_class, _type
            )
            kwargs.setdefault('args', {})
            kwargs['args'].update(self.filtering_args)

            if 'id' not in kwargs['args']:
                id_description = 'Django object unique identification field'
                self.filtering_args.update(
                    {'id': Argument(ID, description=id_description)}
                )
                kwargs['args'].update({'id': Argument(ID, description=id_description)})

        if not kwargs.get('description'):
            kwargs['description'] = f'{_type._meta.model.__name__} list'

        super().__init__(_type, *args, **kwargs)

    @property
    def model(self):
        return self.type._meta.model

    def list_resolver(
        self,
        manager: Manager,
        filterset_class: type[FilterSet],
        filtering_args: Iterable,
        root: graphene.ObjectType | None,
        info: graphene.ResolveInfo,
        **kwargs,
    ) -> DjangoListObjectBase:
        queryset = queryset_factory(manager, root, info, **kwargs)

        filter_kwargs = {k: v for k, v in kwargs.items() if k in filtering_args}

        queryset = filterset_class(
            data=filter_kwargs, queryset=queryset, request=info.context
        ).qs

        count = queryset.count()

        return DjangoListObjectBase(
            count=count,
            results=maybe_queryset(queryset),
            results_field_name=self.type._meta.results_field_name,
        )

    def wrap_resolve(self, parent_resolver: Callable) -> partial[DjangoListObjectBase]:
        if graphql_api_settings.DJANGO_LIST_OBJECT_FIELD_RESOLVER:
            return partial(
                graphql_api_settings.DJANGO_LIST_OBJECT_FIELD_RESOLVER,
                self.type._meta.model._default_manager,
                self.type._meta.results_field_name,
                self.filterset_class,
                self.filtering_args,
            )
        return partial(
            self.list_resolver,
            self.type._meta.model._default_manager,
            self.filterset_class,
            self.filtering_args,
        )
