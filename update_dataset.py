import json
import logging

from datetime import date

import utils

from packaging.version import InvalidVersion, Version


_LOGGER = logging.getLogger(__name__)


def _filter_versions(package, info):
    candidate_versions = []
    for version in info['releases'].keys():
        try:
            version_pep = Version(version)
            candidate_versions.append((version, version_pep))
        except InvalidVersion as e:
            _LOGGER.warning(f'"{package}": {e}')

    candidate_versions.sort(key=lambda x: x[1], reverse=True)
    filtered = []
    upload_date_previous_date = date.max.isoformat()
    for version, _ in candidate_versions:
        upload_date = date.max.isoformat()
        for file in info['releases'][version]:
            upload_date = min(upload_date, file['upload_time'])
        # Keep at most one version per day and do not keep maintenance branch
        # i.e dates shall be in same order as versions
        if upload_date < upload_date_previous_date:
            upload_date_previous_date = upload_date
            filtered.append(version)
    return filtered


def _parse_version(files):
    upload_date = date.max.isoformat()
    pythons = set()
    manylinux = set()
    for file in files:
        upload_date = min(upload_date, file['upload_time'])
        filename = file['filename']
        if not filename.lower().endswith('.whl'):
            continue
        parsed_filename = utils.WHEEL_INFO_RE.match(filename)
        metadata = utils.WheelMetadata(*parsed_filename.groups()[1:])
        for python in metadata.implementation.replace(',', '.').split('.'):
            try:
                int(python[2:])
            except ValueError:
                _LOGGER.warning(
                    f'ignoring python "{python}" for wheel "{filename}"')
                continue
            pythons.add(python)
            if metadata.abi == 'abi3':
                assert python.startswith('cp3')
                # Add abi3 to know that cp3? > {python} are supported
                pythons.add('ab3')
        manylinux.add(metadata.platform)
    python_list = list(pythons)
    python_list.sort(key=lambda x: (int(x[2:]), x[0:2]))
    python_str = ".".join(python_list).replace('ab3', 'abi3')
    manylinux_str = ".".join(sorted(manylinux)).replace('anylinux', 'l')
    return date.fromisoformat(upload_date), python_str, manylinux_str


def _package_update(package):
    cache_file = utils.get_release_cache_path(package)
    if not cache_file.exists():
        return []
    with open(cache_file) as f:
        info = json.load(f)

    versions = _filter_versions(package, info)
    _LOGGER.debug(f'"{package}": using "{versions}"')
    rows = []
    for version in versions:
        week, python, manylinux = _parse_version(info['releases'][version])
        if python == '' or manylinux == '':
            continue
        rows.append(utils.Row(week, package, version, python, manylinux))
    if len(versions) and not len(rows):
        _LOGGER.warning(f'"{package}": no manylinux wheel in "{versions}"')
    return rows


def update(packages):
    rows = []
    for package in packages:
        _LOGGER.info(f'"{package}": begin dataset creation')
        rows.extend(_package_update(package))
        _LOGGER.debug(f'"{package}": end dataset creation')
    return list(sorted(set(r.package for r in rows))), rows