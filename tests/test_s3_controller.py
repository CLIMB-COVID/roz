import moto
from moto.core import set_initial_no_auth_action_count
from roz_scripts import s3_controller
import os
import boto3
from botocore.exceptions import ClientError
import json

import unittest

DIR = os.path.dirname(__file__)

FAKE_VARYS_CFG_PATH = os.path.join(DIR, "fake_varys_cfg.json")
FAKE_ROZ_CFG_PATH = os.path.join(DIR, "fake_roz_cfg.json")
FAKE_AWS_CREDS = os.path.join(DIR, "fake_aws_creds.json")

fake_roz_cfg_dict = {
    "version": "1",
    "pathogen_configs": ["project1", "project2"],
    "configs": {
        "project1": {
            "artifact_layout": "project.sample_name.run_name",
            "files": [".1.fastq.gz", ".2.fastq.gz", ".csv"],
            "sites": ["site1", "site2"],
            "bucket_policies": {
                "site_ingest": ["get", "put", "list", "delete"],
                "site_read": ["get", "list"],
                "project_read": ["get", "list"],
                "project_private": [],
            },
            "site_buckets": {
                "ingest": {
                    "name_layout": "{project}-{site}-{platform}-{test_flag}",
                    "policy": "site_ingest",
                }
            },
            "project_buckets": {
                "fake_files": {
                    "name_layout": "{project}-fake-files",
                    "policy": "project_private",
                },
                "fake_files_2": {
                    "name_layout": "{project}-fake-files-2",
                    "policy": "project_read",
                },
            },
            "file_specs": {
                "illumina": {
                    ".1.fastq.gz": {
                        "sections": 6,
                        "layout": "project.sample_id.run_name.direction.ftype.gzip",
                    },
                    ".2.fastq.gz": {
                        "sections": 6,
                        "layout": "project.sample_id.run_name.direction.ftype.gzip",
                    },
                    ".csv": {
                        "sections": 4,
                        "layout": "project.sample_id.run_name.ftype",
                    },
                    "match_size": 3,
                    "files": [".1.fastq.gz", ".2.fastq.gz", ".csv"],
                },
                "ont": {
                    ".fastq.gz": {
                        "sections": 5,
                        "layout": "project.sample_id.run_name.ftype.gzip",
                    },
                    ".csv": {
                        "sections": 4,
                        "layout": "project.sample_id.run_name.ftype",
                    },
                    "match_size": 2,
                    "files": [".ont.fastq.gz", ".csv"],
                },
            },
        },
        "project2": {
            "artifact_layout": "project.sample_id.run_name",
            "files": [".1.fastq.gz", ".2.fastq.gz", ".csv"],
            "sites": ["site1", "site2"],
            "bucket_policies": {
                "site_ingest": ["get", "put", "list", "delete"],
                "site_read": ["get", "list"],
                "project_read": ["get", "list"],
                "project_private": [],
            },
            "site_buckets": {
                "ingest": {
                    "name_layout": "{project}-{site}-{platform}-{test_flag}",
                    "policy": "site_ingest",
                }
            },
            "project_buckets": {
                "fake_files": {
                    "name_layout": "{project}-fake-files",
                    "policy": "project_private",
                },
                "fake_files_2": {
                    "name_layout": "{project}-fake-files-2",
                    "policy": "project_read",
                },
            },
            "file_specs": {
                "illumina": {
                    ".1.fastq.gz": {
                        "sections": 6,
                        "layout": "project.sample_id.run_name.direction.ftype.gzip",
                    },
                    ".2.fastq.gz": {
                        "sections": 6,
                        "layout": "project.sample_id.run_name.direction.ftype.gzip",
                    },
                    ".csv": {
                        "sections": 4,
                        "layout": "project.sample_id.run_name.ftype",
                    },
                    "match_size": 3,
                    "files": [".1.fastq.gz", ".2.fastq.gz", ".csv"],
                },
                "ont": {
                    ".fastq.gz": {
                        "sections": 5,
                        "layout": "project.sample_id.run_name.ftype.gzip",
                    },
                    ".csv": {
                        "sections": 4,
                        "layout": "project.sample_id.run_name.ftype",
                    },
                    "match_size": 2,
                    "files": [".fastq.gz", ".csv"],
                },
                "pacbio": {
                    ".fastq.gz": {
                        "sections": 5,
                        "layout": "project.sample_id.run_name.ftype.gzip",
                    },
                    ".csv": {
                        "sections": 4,
                        "layout": "project.sample_id.run_name.ftype",
                    },
                    "match_size": 2,
                    "files": [".fastq.gz", ".csv"],
                },
            },
        },
    },
}

fake_aws_cred_dict = {
    "project1": {
        "site1": {
            "aws_access_key_id": "",
            "aws_secret_access_key": "",
            "username": "bryn-site1",
        },
        "site2": {
            "aws_access_key_id": "",
            "aws_secret_access_key": "",
            "username": "bryn-site2",
        },
    },
    "project2": {
        "site1": {
            "aws_access_key_id": "",
            "aws_secret_access_key": "",
            "username": "bryn-site1",
        },
        "site2": {
            "aws_access_key_id": "",
            "aws_secret_access_key": "",
            "username": "bryn-site2",
        },
    },
    "admin": {
        "aws_access_key_id": "",
        "aws_secret_access_key": "",
        "username": "admin",
    },
}


class TestS3Controller(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["MOTO_S3_CUSTOM_ENDPOINTS"] = "https://s3.climb.ac.uk"
        os.environ["FAKE_VARYS_CFG_PATH"] = FAKE_VARYS_CFG_PATH
        os.environ["FAKE_ROZ_CFG_PATH"] = FAKE_ROZ_CFG_PATH

        with open(FAKE_VARYS_CFG_PATH, "w") as f:
            json.dump(fake_aws_cred_dict, f)

        with open(FAKE_ROZ_CFG_PATH, "w") as f:
            json.dump(fake_roz_cfg_dict, f)

        with open(FAKE_AWS_CREDS, "w") as f:
            json.dump(fake_aws_cred_dict, f)

        self.mock_s3 = moto.mock_s3()
        self.mock_s3.start()

        self.s3_client = boto3.client("s3", endpoint_url="https://s3.climb.ac.uk")

    def TearDown(self):
        self.mock_s3.stop()

        self.s3_client.close()

    def test_s3_bucket_exists(self):
        self.s3_client.create_bucket(Bucket="fake_bucket")

        bucket_exists = s3_controller.check_bucket_exists(
            "fake_bucket", fake_aws_cred_dict
        )

        self.assertTrue(bucket_exists)

        bucket_does_not_exist = s3_controller.check_bucket_exists(
            "other_fake_bucket", fake_aws_cred_dict
        )

        self.assertFalse(bucket_does_not_exist)

    def test_s3_create_bucket(self):
        s3_controller.create_bucket(
            "fake_bucket", "project1", "site1", fake_aws_cred_dict
        )

        bucket_exists = s3_controller.check_bucket_exists(
            "fake_bucket", fake_aws_cred_dict
        )

        self.assertTrue(bucket_exists)

    @set_initial_no_auth_action_count(3)
    def test_can_site_list_objects(self):
        self.s3_client.create_bucket(
            Bucket="fake_bucket",
        )

        self.s3_client.put_object(Bucket="fake_bucket", Key="fake_key")

        self.assertTrue(
            s3_controller.can_site_list_objects(
                "fake_bucket",
                fake_aws_cred_dict,
                "project1",
                "site1",
            )
        )

        self.assertFalse(
            s3_controller.can_site_list_objects(
                "fake_bucket", fake_aws_cred_dict, "project1", "site1"
            )
        )

    @set_initial_no_auth_action_count(3)
    def test_can_site_put_objects(self):
        self.s3_client.create_bucket(
            Bucket="fake_bucket",
        )

        self.assertTrue(
            s3_controller.can_site_put_object(
                "fake_bucket",
                fake_aws_cred_dict,
                "project1",
                "site1",
            )
        )

        self.assertFalse(
            s3_controller.can_site_put_object(
                "fake_bucket", fake_aws_cred_dict, "project1", "site1"
            )
        )

    @set_initial_no_auth_action_count(2)
    def test_can_site_create_bucket(self):
        self.assertTrue(
            s3_controller.can_site_create_bucket(
                "fake_bucket", fake_aws_cred_dict, "project1", "site2"
            )
        )

        self.assertFalse(
            s3_controller.can_site_create_bucket(
                "fake_bucket", fake_aws_cred_dict, "project1", "site1"
            )
        )

    def test_create_config_map(self):
        config_map = s3_controller.create_config_map(fake_roz_cfg_dict)
        print(config_map)

        for project, project_config in config_map.items():
            self.assertTrue(
                set(project_config["sites"].keys())
                == set(fake_roz_cfg_dict["configs"][project]["sites"])
            )
            self.assertTrue(
                len(project_config["project_buckets"])
                == len(fake_roz_cfg_dict["configs"][project]["project_buckets"])
            )

            for bucket, bucket_arn in project_config["project_buckets"]:
                splits = bucket_arn.split("-", 1)
                self.assertTrue(splits[0] == project)

            for site, site_config in project_config["sites"].items():
                # Probably aught to be more general
                self.assertTrue(
                    len(site_config["site_buckets"])
                    == (len(fake_roz_cfg_dict["configs"][project]["file_specs"]) * 2)
                )
                for bucket, bucket_arn in site_config["site_buckets"]:
                    splits = bucket_arn.split("-")
                    self.assertTrue(splits[0] == project)
                    self.assertTrue(splits[1] == site)
                    self.assertTrue(
                        splits[2] in fake_roz_cfg_dict["configs"][project]["file_specs"]
                    )
                    self.assertIn(
                        splits[3],
                        ("prod", "test"),
                    )

    def test_check_bucket_exists_and_create(self):
        config_map = s3_controller.create_config_map(fake_roz_cfg_dict)

        s3_controller.check_bucket_exist_and_create(fake_aws_cred_dict, config_map)

        for project, project_config in config_map.items():
            for bucket, bucket_arn in project_config["project_buckets"]:
                self.assertTrue(
                    s3_controller.check_bucket_exists(bucket_arn, fake_aws_cred_dict)
                )

            for site, site_config in project_config["sites"].items():
                for bucket, bucket_arn in site_config["site_buckets"]:
                    self.assertTrue(
                        s3_controller.check_bucket_exists(
                            bucket_arn, fake_aws_cred_dict
                        )
                    )

    def test_bucket_audit(self):
        config_map = s3_controller.create_config_map(fake_roz_cfg_dict)

        s3_controller.check_bucket_exist_and_create(fake_aws_cred_dict, config_map)

        audit = s3_controller.audit_all_buckets(fake_aws_cred_dict, config_map)

        for project, project_config in config_map.items():
            for bucket, bucket_arn in project_config["project_buckets"]:
                self.assertTrue(audit[project]["project_buckets"][(bucket, bucket_arn)])

            for site, site_config in project_config["sites"].items():
                for bucket, bucket_arn in site_config["site_buckets"]:
                    self.assertTrue(
                        audit[project]["site_buckets"][site][(bucket, bucket_arn)]
                    )

    def test_test_policies(self):
        config_map = s3_controller.create_config_map(fake_roz_cfg_dict)

        s3_controller.check_bucket_exist_and_create(fake_aws_cred_dict, config_map)

        audit = s3_controller.audit_all_buckets(fake_aws_cred_dict, config_map)

        policy_results = s3_controller.test_policies(
            audit, config_map, fake_roz_cfg_dict
        )

        print(policy_results)

        self.assertTrue()