from django.conf import settings
from django.test.signals import setting_changed
from rest_framework.settings import APISettings

DEFAULTS = {
    # Pagination
    'DEFAULT_PAGINATION_CLASS': None,  # 'graphene_django_extras.paginations.LimitOffsetGraphqlPagination'
    'DEFAULT_PAGE_SIZE': None,
    'MAX_PAGE_SIZE': None,
    'CLEAN_RESPONSE': False,
    'CACHE_ACTIVE': False,
    'CACHE_TIMEOUT': 300,  # seconds (default 5 min)
    'DJANGO_OBJECT_FIELD_RESOLVER': None,
    'DJANGO_LIST_FIELD_RESOLVER': None,
    'DJANGO_FILTER_LIST_FIELD_RESOLVER': None,
    'DJANGO_FILTER_PAGINATE_LIST_FIELD_RESOLVER': None,
    'DJANGO_LIST_OBJECT_FIELD_RESOLVER': None,
}


# List of settings that may be in string import notation.
IMPORT_STRINGS = (
    'DEFAULT_PAGINATION_CLASS',
    'DJANGO_OBJECT_FIELD_RESOLVER',
    'DJANGO_LIST_FIELD_RESOLVER',
    'DJANGO_FILTER_LIST_FIELD_RESOLVER',
    'DJANGO_FILTER_PAGINATE_LIST_FIELD_RESOLVER',
    'DJANGO_LIST_OBJECT_FIELD_RESOLVER',
)


class GraphQLAPISettings(APISettings):
    MODULE_DOC = 'https://github.com/eamigo86/graphene-django-extras'

    @property
    def user_settings(self):
        if not hasattr(self, '_user_settings'):
            self._user_settings = getattr(settings, 'GRAPHENE_DJANGO_EXTRAS', {})
        return self._user_settings


graphql_api_settings = GraphQLAPISettings(None, DEFAULTS, IMPORT_STRINGS)


def reload_graphql_api_settings(*args, **kwargs):
    global graphql_api_settings  # noqa: PLW0603
    setting, value = kwargs['setting'], kwargs['value']
    if setting == 'GRAPHENE_DJANGO_EXTRAS':
        graphql_api_settings = GraphQLAPISettings(value, DEFAULTS, IMPORT_STRINGS)


setting_changed.connect(reload_graphql_api_settings)
