#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from os import PathLike
import asyncio
from pathlib import Path
from fhir.resources.R4B import bundle
from pydicom import dcmread
from pydicom import dataset
from tqdm import tqdm
import logging
from typing import Iterable, Union, AsyncGenerator
import dicom2fhir.helpers as helpers
from dicom2fhir.helpers import get_or
from dicom2fhir.dicom2fhirbundle import Dicom2FHIRBundle
from dicom2fhir.dicom_json_proxy import DicomJsonProxy

StrPath = Union[str, PathLike]

async def async_rglob_files(base_dir: Path, pattern: str = "*") -> AsyncGenerator[Path, None]:
    loop = asyncio.get_running_loop()
    files = await loop.run_in_executor(None, lambda: list(base_dir.rglob(pattern)))
    for file in files:
        if file.is_file():
            yield file

def is_dicom_file(path: Path) -> bool:
      # Ensure the file can be opened in binary mode
    try:
        with path.open('rb') as f:
            f.seek(128)
            return f.read(4) == b'DICM'
    except Exception:
        return False

async def _parse_directory(dcmDir: StrPath, config: dict) -> AsyncGenerator[DicomJsonProxy, None]:
    """
    Parse a directory of DICOM files including subdirectories and return instances as an AsyncGenerator.

    :param dcmDir: Directory containing DICOM files.
    :return: AsyncGenerator[DicomJsonProxy, None]
    """
    base = Path(dcmDir)
    if not base.is_dir():
        raise ValueError(f"Directory '{dcmDir}' not found")

    skip_invalid_files = get_or(config, "directory_parser.skip_invalid_files", True)

    async for f in async_rglob_files(base, pattern="*"):
        if not f.is_file():
            continue
        if skip_invalid_files and not is_dicom_file(f):
            logging.warning(f"Skipping invalid DICOM file: {f}")
            continue

        try:
            ds = dcmread(f, stop_before_pixels=True, force=True)
            yield DicomJsonProxy(ds.to_json_dict())
        except:
            logging.exception(f"An error occurred while processing DICOM file {f}")
            raise

async def _create_bundle(instances: AsyncGenerator[DicomJsonProxy, None], config: dict = {}) -> bundle.Bundle:

    dcm2fhir = Dicom2FHIRBundle(config=config)
    
    async for ds in instances:
        if not isinstance(ds, DicomJsonProxy):
            raise TypeError("Expected a DicomJsonProxy object")
        dcm2fhir.add(ds)

    return dcm2fhir.create_bundle()

async def from_directory(dcms: StrPath, config: dict = {}) -> bundle.Bundle:
    """
    Process DICOM files into an ImagingStudy FHIR resource.
    
    :param dcms: A directory containing DICOM files.
    :return: ImagingStudy resource.
    """

    def _wrap(instances: Iterable[dataset.Dataset]):
        for instance in instances:
            yield DicomJsonProxy(instance.to_json_dict())

    # use default id function for FHIR resource id generation
    if 'id_function' not in config:
        config['id_function'] = helpers.default_id_function()

    # parse directory of DICOM files
    if isinstance(dcms, StrPath):
        if not Path(dcms).is_dir():
            raise ValueError(f"Expected a directory, got: {dcms}")
        dicom_json_proxies = _parse_directory(dcms, config)
        return await _create_bundle(dicom_json_proxies, config)
    # use iterable of DICOM JSON Proxies
    else:
        # guard against non-iterable or non-dict types
        if not isinstance(dcms, Iterable):
            raise TypeError("Expected an iterable of dicts. Got: {}".format(type(dcms)))
        for d in dcms:
            if not isinstance(d, dict):
                raise TypeError("Expected a dict. Got: {}".format(type(d)))

        dicom_json_proxies = [DicomJsonProxy(d) for d in dcms]
        return _create_bundle(dicom_json_proxies, config)

async def from_generator(dcms: AsyncGenerator[dict, None], config: dict = {}) -> bundle.Bundle:
    """
    Process DICOM files or datasets into an ImagingStudy FHIR resource.
    
    :param dcms: AsyncGenerator of DICOM JSON dicts.
    :return: ImagingStudy resource.
    """

    # use default id function for FHIR resource id generation
    if 'id_function' not in config:
        config['id_function'] = helpers.default_id_function()

    # guard against non-iterable or non-dict types
    if not isinstance(dcms, AsyncGenerator):
        raise TypeError("Expected an async generator of dicts. Got: {}".format(type(dcms)))

    async def _to_dicom_json_proxy(dcms: AsyncGenerator[dict, None]) -> AsyncGenerator[DicomJsonProxy, None]:
        async for d in dcms:
            yield DicomJsonProxy(d)

    dicom_json_proxies = _to_dicom_json_proxy(dcms)
    return await _create_bundle(dicom_json_proxies, config)