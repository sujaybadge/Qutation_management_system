from django import template

register = template.Library()

@register.filter
def split_lines(value):
    """Split text by newlines and return a list of non-empty lines."""
    if not value:
        return []
    return [line.strip() for line in value.split('\n') if line.strip()]
