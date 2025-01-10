import random

from graphql import GraphQLArgument, GraphQLInt, GraphQLNonNull

from .base import BaseExtraGraphQLDirective

__all__ = ('SampleGraphQLDirective', 'ShuffleGraphQLDirective')


class ShuffleGraphQLDirective(BaseExtraGraphQLDirective):
    """
    Shuffle the list in place
    """

    @staticmethod
    def resolve(value, directive, root, info, **kwargs):
        if value:
            random.shuffle(value)

        return value


class SampleGraphQLDirective(BaseExtraGraphQLDirective):
    @staticmethod
    def get_args():
        return {
            'k': GraphQLArgument(
                GraphQLNonNull(GraphQLInt), description='Value to default to'
            )
        }

    @staticmethod
    def resolve(value, directive, root, info, **kwargs):
        k_argument = next(arg for arg in directive.arguments if arg.name.value == 'k')
        k = int(k_argument.value.value)
        return random.sample(value, k) if value else value
