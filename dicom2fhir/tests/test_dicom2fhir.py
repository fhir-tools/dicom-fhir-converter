import os
import yaml
import logging
import unittest
from pathlib import Path
from .. import dicom2fhir
from fhir.resources.R4B import bundle
from fhir.resources.R4B import imagingstudy
from dicom2fhir.dicom_json_proxy import DicomJsonProxy
from pydicom import dcmread

dicom2fhir_config = {
    "dicom_timezone": "Europe/Berlin",
    "generator": {
        "imaging_study": {
            "add_instance": True,
        }
    }
}

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def _extract_imaging_study_from_bundle(b: bundle.Bundle) -> imagingstudy.ImagingStudy:
    """
    Extract the ImagingStudy resource from a FHIR Bundle.
    """
    if not isinstance(b, bundle.Bundle):
        raise TypeError("Expected a Bundle resource")

    for entry in (b.entry or []):
        if entry.resource and isinstance(entry.resource, imagingstudy.ImagingStudy):
            return entry.resource

    raise ValueError("No ImagingStudy resource found in the bundle")

class testDicom2FHIR(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Set up any necessary configuration or environment variables
        with open(Path(__file__).parent / "config.yaml") as f:
            self.config = yaml.safe_load(f)

        if not self.config:
            raise ValueError("Configuration could not be loaded")

    async def test_dicom_json_proxy(self):

        # Test 1
        dcm_file = os.path.join(os.getcwd(), "dicom2fhir", "tests", "resources", "dcm-instance", "dcm_1.dcm")
        dicom_json = dcmread(dcm_file, stop_before_pixels=True, force=True).to_json_dict()
        dicom_json_proxy = DicomJsonProxy(dicom_json)

        pat_id = dicom_json_proxy.PatientID
        self.assertIsNotNone(pat_id, "PatientID should not be None")
        self.assertIsInstance(pat_id, str, "PatientID should be a string")
        self.assertTrue(pat_id == "DAC007_CRLAT", "PatientID should be DAC007_CRLAT")

        kvp = dicom_json_proxy.KVP

        logger.info(f"KVP: {kvp}, type: {type(kvp)}")

        # Test 2
        dicom_json = {
            "00200060": {
                "vr": "CS"
            }
        }
        dicom_json_proxy = DicomJsonProxy(dicom_json)
        self.assertFalse(dicom_json_proxy.non_empty("Laterality"), "Laterality should be empty")


    async def test_instance_dicom2fhir(self):
        dcmDir = os.path.join(os.getcwd(), "dicom2fhir", "tests", "resources", "dcm-instance")
        study: imagingstudy.ImagingStudy
        bundle = await dicom2fhir.from_directory(dcmDir, config=self.config)
        study = _extract_imaging_study_from_bundle(bundle)

        self.assertIsNotNone(study, "No ImagingStudy was generated")
        self.assertEqual(study.numberOfSeries, 1, "Number of Series in the study mismatch")
        self.assertEqual(study.numberOfInstances, 1, "Number of Instances in the study mismatch")
        self.assertIsNotNone(study.series, "Series was not built for the study")
        self.assertIsNotNone(study.modality, "Modality is missing")
        self.assertEqual(len(study.modality), 1, "Series must list only one modality")
        self.assertEqual(study.modality[0].code, "CR", "Incorrect modality detected")
        self.assertEqual(len(study.series), 1, "Number objects in Series Array: mismatch")
        self.assertEqual(len(study.series[0].instance), 1, "Number objects in Instance Array: mismatch")

        series: imagingstudy.ImagingStudySeries
        series = study.series[0]
        self.assertIsNotNone(series, "Missing Series")
        self.assertIsNotNone(series.bodySite, "Body site is missing")
        self.assertEqual(series.bodySite.code, '43799004', "Expected SNOMED code for CHEST")
        self.assertIsNotNone(series.bodySite.display, "BodySite display is missing")
        self.assertEqual(series.bodySite.display, 'Chest', "Chest is expected as body site")

        instance: imagingstudy.ImagingStudySeriesInstance
        instance = series.instance[0]
        self.assertIsNotNone(instance, "Missing Instance")

    async def test_multi_instance_dicom(self):
        dcmDir = os.path.join(os.getcwd(), "dicom2fhir", "tests", "resources", "dcm-multi-instance")
        bundle = await dicom2fhir.from_directory(dcmDir, config=self.config)

        #print(bundle.model_dump_json(indent=2))

        study = _extract_imaging_study_from_bundle(bundle)

        self.assertIsNotNone(study, "No ImagingStudy was generated")
        self.assertEqual(study.numberOfSeries, 1)
        self.assertEqual(study.numberOfInstances, 5)
        self.assertIsNotNone(study.series, "Series was not built for the study")
        self.assertEqual(len(study.modality), 1, "Only single modality expected for this study")
        self.assertEqual(study.modality[0].code, "CR")
        self.assertEqual(len(study.series), 1, "Incorrect number of series detected")
        self.assertEqual(len(study.series[0].instance), 5, "Incorrect number of instances detected")

    async def test_multi_series_dicom(self):
        dcmDir = os.path.join(os.getcwd(), "dicom2fhir", "tests", "resources", "dcm-multi-series")
        bundle = await dicom2fhir.from_directory(dcmDir, config=self.config)

        #print(bundle.model_dump_json(indent=2))

        study = _extract_imaging_study_from_bundle(bundle)

        self.assertIsNotNone(study, "No ImagingStudy was generated")
        self.assertEqual(study.numberOfSeries, 4, "Number of Series in the study mismatch")
        self.assertEqual(study.numberOfInstances, 4, "Number of Instances in the study mismatch")
        self.assertIsNotNone(study.series, "Series was not built for the study")
        self.assertEqual(len(study.modality), 1, "Only single modality expected for this study")
        self.assertEqual(study.modality[0].code, "CR", "Incorrect Modality detected")
        self.assertEqual(len(study.series), 4, "Number of series in the study: mismatch")
