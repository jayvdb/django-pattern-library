import os
import re
import operator

from django.template import TemplateDoesNotExist
from django.template.loader import get_template, render_to_string
from django.template.loaders.app_directories import get_app_template_dirs
from django.utils.safestring import mark_safe

import markdown
import yaml

from pattern_library import (
    get_pattern_context_var_name,
    get_pattern_template_suffix,
    get_sections,
)
from pattern_library.exceptions import TemplateIsNotPattern


def path_to_section():
    section_config = get_sections()
    sections = {}
    for section, paths in section_config:
        for path in paths:
            sections[path] = section
    return sections


def is_pattern(template_name):
    return template_name.endswith(get_pattern_template_suffix())


def is_pattern_type(template_name, pattern_type):
    if not is_pattern(template_name):
        return False

    substring = '/{}/'.format(pattern_type)
    return substring in template_name


def is_pattern_library_context(context):
    context_var_name = get_pattern_context_var_name()

    return context.get(context_var_name) is True


def section_for(template_folder):
    paths = path_to_section()
    for path in paths:
        if template_folder.startswith(path):
            return paths[path], path
    return None, None


def base_dict():
    return {'templates_stored': [], 'template_groups': {}}


def order_dict(dictionary, key_sort=None):
    # Order a dictionary by the keys
    values = list(dictionary.items())
    if not key_sort:
        values.sort(key=operator.itemgetter(0))
    else:
        values.sort(key=lambda key: key_sort(key[0]))
    return dict(values)


def get_pattern_templates():
    templates = base_dict()
    template_dirs = get_app_template_dirs('templates')

    for lookup_dir in template_dirs:
        for root, dirs, files in os.walk(lookup_dir, topdown=True):
            # Ignore folders without files
            if not files:
                continue

            base_path = os.path.relpath(root, lookup_dir)
            section, path = section_for(base_path)

            # It has no section, ignore it
            if not section:
                continue

            found_templates = []
            for current_file in files:
                pattern_path = os.path.join(root, current_file)
                pattern_path = os.path.relpath(pattern_path, lookup_dir)

                if is_pattern(pattern_path):
                    template = get_template(pattern_path)
                    pattern_config = get_pattern_config(pattern_path)
                    pattern_name = pattern_config.get('name')
                    if pattern_name:
                        template.pattern_name = pattern_name
                    found_templates.append(template)

            if found_templates:
                sub_folders = os.path.relpath(root, lookup_dir)
                sub_folders = sub_folders.replace(path, '')
                templates_to_store = templates
                for folder in [section, *sub_folders.split(os.sep)]:
                    try:
                        templates_to_store = templates_to_store['template_groups'][folder]
                    except KeyError:
                        templates_to_store['template_groups'][folder] = base_dict()
                        templates_to_store = templates_to_store['template_groups'][folder]

                templates_to_store['templates_stored'].extend(found_templates)

    # Order the templates alphabetically
    for templates_objs in templates['template_groups'].values():
        templates_objs['template_groups'] = order_dict(templates_objs['template_groups'])

    # Order the top level by the sections
    section_order = [section for section, _ in get_sections()]
    templates['template_groups'] = order_dict(
        templates['template_groups'],
        key_sort=lambda key: section_order.index(key)
    )

    return templates


def get_pattern_config_str(template_name):
    replace_pattern = '{}$'.format(get_pattern_template_suffix())
    context_path = re.sub(replace_pattern, '', template_name)

    context_name = context_path + '.yaml'
    try:
        context_file = get_template(context_name)
    except TemplateDoesNotExist:
        return ''

    return context_file.render()


def get_pattern_config(template_name):
    config_str = get_pattern_config_str(template_name)
    if config_str:
        return yaml.load(config_str, Loader=yaml.FullLoader)
    return {}


def mark_context_strings_safe(value, parent=None, subscript=None):
    if isinstance(value, list):
        for index, sub_value in enumerate(value):
            mark_context_strings_safe(sub_value, parent=value, subscript=index)

    elif isinstance(value, dict):
        for key, sub_value in value.items():
            mark_context_strings_safe(sub_value, parent=value, subscript=key)

    elif isinstance(value, str):
        parent[subscript] = mark_safe(value)


def get_pattern_context(template_name):
    config = get_pattern_config(template_name)
    context = config.get('context', {})

    mark_context_strings_safe(context)

    return context


def get_pattern_markdown(template_name):
    replace_pattern = '{}$'.format(get_pattern_template_suffix())
    md_file = re.sub(replace_pattern, '', template_name)

    md_file = md_file + '.md'
    md_file = os.path.join(get_pattern_template_dir(), md_file)

    try:
        # Default encoding is platform-dependant, so we explicitly open it as utf-8.
        with open(md_file, 'r', encoding='utf-8') as f:
            htmlmarkdown = markdown.markdown(f.read())
            return htmlmarkdown
    except IOError:
        return ''


def render_pattern(request, template_name):
    if not is_pattern(template_name):
        raise TemplateIsNotPattern

    context = get_pattern_context(template_name)
    context[get_pattern_context_var_name()] = True
    return render_to_string(template_name, request=request, context=context)
