import unittest
from unittest.mock import Mock, mock_open, patch, MagicMock, call

from roz_scripts import s3_matcher, ingest, mscape_ingest_validation

from types import SimpleNamespace
import multiprocessing as mp
import time
import os
import json
from varys import varys
from moto import mock_s3
from moto.server import ThreadedMotoServer
import boto3
import uuid
import pika

DIR = os.path.dirname(__file__)
S3_MATCHER_LOG_FILENAME = os.path.join(DIR, "s3_matcher.log")
ROZ_INGEST_LOG_FILENAME = os.path.join(DIR, "ingest.log")
TEST_MESSAGE_LOG_FILENAME = os.path.join(DIR, "test_messages.log")

TEST_CSV_FILENAME = os.path.join(DIR, "test.csv")

VARYS_CFG_PATH = os.path.join(DIR, "varys_cfg.json")
TEXT = "Hello, world!"

example_csv_msg = {
    "Records": [
        {
            "eventVersion": "2.2",
            "eventSource": "ceph:s3",
            "awsRegion": "",
            "eventTime": "2023-10-10T06:39:35.470367Z",
            "eventName": "ObjectCreated:Put",
            "userIdentity": {"principalId": "testuser"},
            "requestParameters": {"sourceIPAddress": ""},
            "responseElements": {
                "x-amz-request-id": "testdata",
                "x-amz-id-2": "testdata",
            },
            "s3": {
                "s3SchemaVersion": "1.0",
                "configurationId": "inbound.s3",
                "bucket": {
                    "name": "mscapetest-birm-ont-prod",
                    "ownerIdentity": {"principalId": "testuser"},
                    "arn": "arn:aws:s3:::mscapetest-birm-ont-prod",
                    "id": "testdata",
                },
                "object": {
                    "key": "mscapetest.sample-test.run-test.ont.csv",
                    "size": 275,
                    "eTag": "7022ea6a3adb39323b5039c1d6587d08",
                    "versionId": "",
                    "sequencer": "testdata",
                    "metadata": [
                        {"key": "x-amz-content-sha256", "val": "UNSIGNED-PAYLOAD"},
                        {"key": "x-amz-date", "val": "testdata"},
                    ],
                    "tags": [],
                },
            },
            "eventId": "testdata",
            "opaqueData": "",
        }
    ]
}

example_csv_msg_2 = {
    "Records": [
        {
            "eventVersion": "2.2",
            "eventSource": "ceph:s3",
            "awsRegion": "",
            "eventTime": "2023-10-10T06:39:35.470367Z",
            "eventName": "ObjectCreated:Put",
            "userIdentity": {"principalId": "testuser"},
            "requestParameters": {"sourceIPAddress": ""},
            "responseElements": {
                "x-amz-request-id": "testdata",
                "x-amz-id-2": "testdata",
            },
            "s3": {
                "s3SchemaVersion": "1.0",
                "configurationId": "inbound.s3",
                "bucket": {
                    "name": "mscapetest-birm-ont-prod",
                    "ownerIdentity": {"principalId": "testuser"},
                    "arn": "arn:aws:s3:::mscapetest-birm-ont-prod",
                    "id": "testdata",
                },
                "object": {
                    "key": "mscapetest.sample-test.run-test.ont.csv",
                    "size": 275,
                    "eTag": "29d33a6a67446891caf00d228b954ba7",
                    "versionId": "",
                    "sequencer": "testdata",
                    "metadata": [
                        {"key": "x-amz-content-sha256", "val": "UNSIGNED-PAYLOAD"},
                        {"key": "x-amz-date", "val": "testdata"},
                    ],
                    "tags": [],
                },
            },
            "eventId": "testdata",
            "opaqueData": "",
        }
    ]
}

example_fastq_msg = {
    "Records": [
        {
            "eventVersion": "2.2",
            "eventSource": "ceph:s3",
            "awsRegion": "",
            "eventTime": "2023-10-10T06:39:35.470367Z",
            "eventName": "ObjectCreated:Put",
            "userIdentity": {"principalId": "testuser"},
            "requestParameters": {"sourceIPAddress": ""},
            "responseElements": {
                "x-amz-request-id": "testdata",
                "x-amz-id-2": "testdata",
            },
            "s3": {
                "s3SchemaVersion": "1.0",
                "configurationId": "inbound.s3",
                "bucket": {
                    "name": "mscapetest-birm-ont-prod",
                    "ownerIdentity": {"principalId": "testuser"},
                    "arn": "arn:aws:s3:::mscapetest-birm-ont-prod",
                    "id": "testdata",
                },
                "object": {
                    "key": "mscapetest.sample-test.run-test.fastq.gz",
                    "size": 123123123,
                    "eTag": "179d94f8cd22896c2a80a9a7c98463d2-21",
                    "versionId": "",
                    "sequencer": "testdata",
                    "metadata": [
                        {"key": "x-amz-content-sha256", "val": "UNSIGNED-PAYLOAD"},
                        {"key": "x-amz-date", "val": "testdata"},
                    ],
                    "tags": [],
                },
            },
            "eventId": "testdata",
            "opaqueData": "",
        }
    ]
}

incorrect_fastq_msg = {
    "Records": [
        {
            "eventVersion": "2.2",
            "eventSource": "ceph:s3",
            "awsRegion": "",
            "eventTime": "2023-10-10T06:39:35.470367Z",
            "eventName": "ObjectCreated:Put",
            "userIdentity": {"principalId": "testuser"},
            "requestParameters": {"sourceIPAddress": ""},
            "responseElements": {
                "x-amz-request-id": "testdata",
                "x-amz-id-2": "testdata",
            },
            "s3": {
                "s3SchemaVersion": "1.0",
                "configurationId": "inbound.s3",
                "bucket": {
                    "name": "mscapetest-birm-ont-prod",
                    "ownerIdentity": {"principalId": "testuser"},
                    "arn": "arn:aws:s3:::mscapetest-birm-ont-prod",
                    "id": "testdata",
                },
                "object": {
                    "key": "mscapetest.sample-test-2.run-test.fastq.gz",
                    "size": 123123123,
                    "eTag": "179d94f8cd22896c2a80a9a7c98463d2-21",
                    "versionId": "",
                    "sequencer": "testdata",
                    "metadata": [
                        {"key": "x-amz-content-sha256", "val": "UNSIGNED-PAYLOAD"},
                        {"key": "x-amz-date", "val": "testdata"},
                    ],
                    "tags": [],
                },
            },
            "eventId": "testdata",
            "opaqueData": "",
        }
    ]
}

example_match_message = {
    "uuid": "42c3796d-d767-4293-97a8-c4906bb5cca8",
    "payload_version": 1,
    "site": "birm",
    "uploaders": ["testuser"],
    "match_timestamp": 1697036668222422871,
    "artifact": "mscapetest.sample-test.run-test",
    "sample_id": "sample-test",
    "run_name": "run-test",
    "project": "mscapetest",
    "platform": "ont",
    "files": {
        ".fastq.gz": {
            "uri": "s3://mscapetest-birm-ont-prod/mscapetest.sample-test.run-test.fastq.gz",
            "etag": "179d94f8cd22896c2a80a9a7c98463d2-21",
            "key": "mscapetest.sample-test.run-test.fastq.gz",
        },
        ".csv": {
            "uri": "s3://mscapetest-birm-ont-prod/mscapetest.sample-test.run-test.ont.csv",
            "etag": "7022ea6a3adb39323b5039c1d6587d08",
            "key": "mscapetest.sample-test.run-test.ont.csv",
        },
    },
    "test_flag": False,
}

example_mismatch_match_message = {
    "uuid": "42c3796d-d767-4293-97a8-c4906bb5cca8",
    "payload_version": 1,
    "site": "birm",
    "uploaders": ["testuser"],
    "match_timestamp": 1697036668222422871,
    "artifact": "mscapetest.sample-test-2.run-test-2",
    "sample_id": "sample-test-2",
    "run_name": "run-test-2",
    "project": "mscapetest",
    "platform": "ont",
    "files": {
        ".fastq.gz": {
            "uri": "s3://mscapetest-birm-ont-prod/mscapetest.sample-test-2.run-test-2.fastq.gz",
            "etag": "179d94f8cd22896c2a80a9a7c98463d2-21",
            "key": "mscapetest.sample-test-2.run-test-2.fastq.gz",
        },
        ".csv": {
            "uri": "s3://mscapetest-birm-ont-prod/mscapetest.sample-test.run-test.ont.csv",
            "etag": "7022ea6a3adb39323b5039c1d6587d08",
            "key": "mscapetest.sample-test.run-test.ont.csv",
        },
    },
    "test_flag": False,
}

example_validator_message = {
    "uuid": "b7a4bf27-9305-40e4-9b6b-ed4eb8f5dca6",
    "artifact": "mscapetest.sample-test.run-test",
    "sample_id": "sample-test",
    "run_name": "run-test",
    "project": "mscapetest",
    "uploaders": ["mscape-testuser"],
    "platform": "ont",
    "ingest_timestamp": 1694780451766213337,
    "cid": False,
    "site": "birm",
    "created": False,
    "ingested": False,
    "files": {
        ".fastq.gz": {
            "uri": "s3://mscapetest-birm-ont-prod/mscapetest.sample-test.run-test.fastq.gz",
            "etag": "179d94f8cd22896c2a80a9a7c98463d2-21",
            "key": "mscapetest.sample-test.run-test.fastq.gz",
        },
        ".csv": {
            "uri": "s3://mscapetest-birm-ont-prod/mscapetest.sample-test.run-test.ont.csv",
            "etag": "7022ea6a3adb39323b5039c1d6587d08",
            "key": "mscapetest.sample-test.run-test.ont.csv",
        },
    },
    "onyx_test_status_code": 201,
    "onyx_test_create_errors": {},
    "onyx_test_create_status": True,
    "validate": True,
    "onyx_status_code": False,
    "onyx_errors": {},
    "onyx_create_status": False,
    "ingest_errors": [],
    "test_flag": False,
    "test_ingest_result": False,
}

example_test_validator_message = {
    "uuid": "b7a4bf27-9305-40e4-9b6b-ed4eb8f5dca6",
    "artifact": "mscapetest.sample-test.run-test",
    "sample_id": "sample-test",
    "run_name": "run-test",
    "project": "mscapetest",
    "uploaders": ["mscape-testuser"],
    "platform": "ont",
    "ingest_timestamp": 1694780451766213337,
    "cid": False,
    "site": "birm",
    "created": False,
    "ingested": False,
    "files": {
        ".fastq.gz": {
            "uri": "s3://mscapetest-birm-ont-prod/mscapetest.sample-test.run-test.fastq.gz",
            "etag": "179d94f8cd22896c2a80a9a7c98463d2-21",
            "key": "mscapetest.sample-test.run-test.fastq.gz",
        },
        ".csv": {
            "uri": "s3://mscapetest-birm-ont-prod/mscapetest.sample-test.run-test.ont.csv",
            "etag": "7022ea6a3adb39323b5039c1d6587d08",
            "key": "mscapetest.sample-test.run-test.ont.csv",
        },
    },
    "onyx_test_status_code": 201,
    "onyx_test_create_errors": {},
    "onyx_test_create_status": True,
    "validate": True,
    "onyx_status_code": False,
    "onyx_errors": {},
    "onyx_create_status": False,
    "ingest_errors": [],
    "test_flag": True,
    "test_ingest_result": False,
}

example_execution_trace = """task_id	hash	native_id	name	status	exit	submit	duration	realtime	%cpu	peak_rss	peak_vmem	rchar	wchar
2	88/1abc3f	nf-881abc3f59bf578b7e0aa4e6b409e936	ingest:kraken_pipeline:run_kraken_and_bracken:determine_bracken_length	COMPLETED	0	2023-09-15 04:08:18.717	13.3s	3.4s	2.3%	3.2 MB	5.6 MB	85.6 KB	472 B
1	13/ffbf02	nf-13ffbf024c264c53f1fc73d8127df00c	ingest:fastp_paired (1)	COMPLETED	0	2023-09-15 04:08:27.882	2m 24s	2m 6s	546.7%	2.6 GB	3.1 GB	13.4 GB	13.2 GB
3	62/dda4b3	nf-62dda4b32420ecddcf2aee1de8e9b423	ingest:paired_concatenate (1)	COMPLETED	0	2023-09-15 04:10:58.524	5m 35s	5m 17s	164.2%	38.3 MB	232.7 MB	12.6 GB	12.5 GB
4	66/50cebb	nf-6650cebb7a8caf2a21cc57d9ad28a48e	ingest:kraken_pipeline:qc_checks:read_stats (1)	COMPLETED	0	2023-09-15 04:16:38.492	2m 9s	1m 54s	98.5%	6.1 MB	11 MB	3 GB	10.9 GB
6	51/510a2b	nf-51510a2bafede6b088237c8d1ba4b01e	ingest:kraken_pipeline:qc_checks:combine_stats (1)	COMPLETED	0	2023-09-15 04:19:03.509	35.5s	20.7s	114.4%	199.7 MB	12.9 GB	2.7 GB	1.4 GB
5	91/c305e2	nf-91c305e22a18d1362fbd90c3a9ecdb3f	ingest:kraken_pipeline:run_kraken_and_bracken:kraken2_client (1)	COMPLETED	0	2023-09-15 04:16:38.746	19m 24s	19m 15s	33.0%	695.2 MB	1.2 GB	3 GB	1.4 GB
7	8d/8d5d7b	nf-8d8d5d7b4d994f3c81aba6cbcd94200a	ingest:kraken_pipeline:run_kraken_and_bracken:combine_kraken_outputs	COMPLETED	0	2023-09-15 04:36:08.725	38.3s	21.9s	149.7%	58.2 MB	12.7 GB	1.4 GB	1.4 GB
8	33/b742de	nf-33b742dee3413d67186dfc1ef7187914	ingest:kraken_pipeline:run_kraken_and_bracken:bracken	COMPLETED	0	2023-09-15 04:36:48.809	10.2s	0ms	94.9%	6.1 MB	10.8 MB	4.1 MB	802.3 KB
9	24/8ce934	nf-248ce9347747953fa4c71ed275e35463	ingest:kraken_pipeline:run_kraken_and_bracken:bracken_to_json	COMPLETED	0	2023-09-15 04:37:03.642	18.4s	3.6s	194.7%	679.7 MB	1.4 GB	394.7 MB	4 MB
11	a2/f41a10	nf-a2f41a105cdc1416d6d5b49cd98228e7	ingest:kraken_pipeline:generate_report:make_report (1)	COMPLETED	0	2023-09-15 04:37:28.660	22.3s	5.2s	240.2%	3.2 MB	5.6 MB	6.3 MB	755.2 KB
10	44/646e08	nf-44646e080dd2f81a22feacd597bb4f6c	ingest:extract_paired_reads (1)	COMPLETED	0	2023-09-15 04:37:03.713	2m 35s	2m 21s	-	-	-	-	-
"""

example_execution_trace_human = """task_id	hash	native_id	name	status	exit	submit	duration	realtime	%cpu	peak_rss	peak_vmem	rchar	wchar
2	88/1abc3f	nf-881abc3f59bf578b7e0aa4e6b409e936	ingest:kraken_pipeline:run_kraken_and_bracken:determine_bracken_length	COMPLETED	0	2023-09-15 04:08:18.717	13.3s	3.4s	2.3%	3.2 MB	5.6 MB	85.6 KB	472 B
1	13/ffbf02	nf-13ffbf024c264c53f1fc73d8127df00c	ingest:fastp_paired (1)	COMPLETED	0	2023-09-15 04:08:27.882	2m 24s	2m 6s	546.7%	2.6 GB	3.1 GB	13.4 GB	13.2 GB
3	62/dda4b3	nf-62dda4b32420ecddcf2aee1de8e9b423	ingest:paired_concatenate (1)	COMPLETED	0	2023-09-15 04:10:58.524	5m 35s	5m 17s	164.2%	38.3 MB	232.7 MB	12.6 GB	12.5 GB
4	66/50cebb	nf-6650cebb7a8caf2a21cc57d9ad28a48e	ingest:kraken_pipeline:qc_checks:read_stats (1)	COMPLETED	0	2023-09-15 04:16:38.492	2m 9s	1m 54s	98.5%	6.1 MB	11 MB	3 GB	10.9 GB
6	51/510a2b	nf-51510a2bafede6b088237c8d1ba4b01e	ingest:kraken_pipeline:qc_checks:combine_stats (1)	COMPLETED	0	2023-09-15 04:19:03.509	35.5s	20.7s	114.4%	199.7 MB	12.9 GB	2.7 GB	1.4 GB
5	91/c305e2	nf-91c305e22a18d1362fbd90c3a9ecdb3f	ingest:kraken_pipeline:run_kraken_and_bracken:kraken2_client (1)	COMPLETED	0	2023-09-15 04:16:38.746	19m 24s	19m 15s	33.0%	695.2 MB	1.2 GB	3 GB	1.4 GB
7	8d/8d5d7b	nf-8d8d5d7b4d994f3c81aba6cbcd94200a	ingest:kraken_pipeline:run_kraken_and_bracken:combine_kraken_outputs	COMPLETED	0	2023-09-15 04:36:08.725	38.3s	21.9s	149.7%	58.2 MB	12.7 GB	1.4 GB	1.4 GB
8	33/b742de	nf-33b742dee3413d67186dfc1ef7187914	ingest:kraken_pipeline:run_kraken_and_bracken:bracken	COMPLETED	0	2023-09-15 04:36:48.809	10.2s	0ms	94.9%	6.1 MB	10.8 MB	4.1 MB	802.3 KB
9	24/8ce934	nf-248ce9347747953fa4c71ed275e35463	ingest:kraken_pipeline:run_kraken_and_bracken:bracken_to_json	COMPLETED	0	2023-09-15 04:37:03.642	18.4s	3.6s	194.7%	679.7 MB	1.4 GB	394.7 MB	4 MB
11	a2/f41a10	nf-a2f41a105cdc1416d6d5b49cd98228e7	ingest:kraken_pipeline:generate_report:make_report (1)	COMPLETED	0	2023-09-15 04:37:28.660	22.3s	5.2s	240.2%	3.2 MB	5.6 MB	6.3 MB	755.2 KB
10	44/646e08	nf-44646e080dd2f81a22feacd597bb4f6c	ingest:extract_paired_reads (1)	FAILED	2	2023-09-15 04:37:03.713	2m 35s	2m 21s	-	-	-	-	-
"""

example_reads_summary = [
    {
        "human_readable": "Pseudomonas",
        "taxon": "286",
        "tax_level": "G",
        "filenames": ["reads.286.fastq"],
        "qc_metrics": {
            "num_reads": 20188,
            "avg_qual": 37.19427382603527,
            "mean_len": 249.46433524866256,
        },
    }
]


class MockResponse:
    def __init__(self, status_code, json_data=None, ok=True):
        self.status_code = status_code
        self.json_data = json_data
        self.ok = ok

    def json(self):
        return self.json_data


class Test_S3_matcher(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

        config = {
            "version": "0.1",
            "profiles": {
                "roz": {
                    "username": "guest",
                    "password": "guest",
                    "amqp_url": "127.0.0.1",
                    "port": 5672,
                }
            },
        }

        with open(VARYS_CFG_PATH, "w") as f:
            json.dump(config, f, ensure_ascii=False)

        os.environ["VARYS_CFG"] = VARYS_CFG_PATH
        os.environ["S3_MATCHER_LOG"] = S3_MATCHER_LOG_FILENAME
        os.environ["INGEST_LOG_LEVEL"] = "DEBUG"
        os.environ["ROZ_CONFIG_JSON"] = "config/config.json"
        os.environ["ONYX_ROZ_PASSWORD"] = "password"
        os.environ["ROZ_INGEST_LOG"] = ROZ_INGEST_LOG_FILENAME

        self.varys_client = varys("roz", TEST_MESSAGE_LOG_FILENAME)

    def tearDown(self):
        self.varys_client.close()
        self.s3_matcher_process.kill()

        credentials = pika.PlainCredentials("guest", "guest")

        connection = pika.BlockingConnection(
            pika.ConnectionParameters("localhost", credentials=credentials)
        )
        channel = connection.channel()

        channel.queue_delete(queue="inbound.s3")
        channel.queue_delete(queue="inbound.matched")

        connection.close()
        time.sleep(1)

    def test_s3_successful_match(self):
        args = SimpleNamespace(sleep_time=5)

        self.s3_matcher_process = mp.Process(target=s3_matcher.run, args=(args,))
        self.s3_matcher_process.start()

        self.varys_client.send(
            example_csv_msg, exchange="inbound.s3", queue_suffix="s3_matcher"
        )
        self.varys_client.send(
            example_fastq_msg, exchange="inbound.s3", queue_suffix="s3_matcher"
        )

        message = self.varys_client.receive(
            exchange="inbound.matched",
            queue_suffix="s3_matcher",
            timeout=20,
        )

        self.assertIsNotNone(message)
        message_dict = json.loads(message.body)

        self.assertEqual(message_dict["sample_id"], "sample-test")
        self.assertEqual(message_dict["artifact"], "mscapetest.sample-test.run-test")
        self.assertEqual(message_dict["run_name"], "run-test")
        self.assertEqual(message_dict["project"], "mscapetest")
        self.assertEqual(message_dict["platform"], "ont")
        self.assertEqual(message_dict["site"], "birm")
        self.assertEqual(message_dict["uploaders"], ["testuser"])
        self.assertEqual(
            message_dict["files"][".csv"]["key"],
            "mscapetest.sample-test.run-test.ont.csv",
        )
        self.assertEqual(
            message_dict["files"][".fastq.gz"]["key"],
            "mscapetest.sample-test.run-test.fastq.gz",
        )
        self.assertTrue(uuid.UUID(message_dict["uuid"], version=4))

    def test_s3_incorrect_match(self):
        args = SimpleNamespace(sleep_time=5)

        self.s3_matcher_process = mp.Process(target=s3_matcher.run, args=(args,))
        self.s3_matcher_process.start()

        self.varys_client.send(
            example_csv_msg, exchange="inbound.s3", queue_suffix="s3_matcher"
        )
        self.varys_client.send(
            incorrect_fastq_msg, exchange="inbound.s3", queue_suffix="s3_matcher"
        )

        message = self.varys_client.receive(
            exchange="inbound.matched",
            queue_suffix="s3_matcher",
            timeout=10,
        )
        self.assertIsNone(message)

    def test_s3_updated_csv(self):
        with patch("roz_scripts.s3_matcher.OnyxClient") as mock_client:
            mock_client.return_value.__enter__.return_value._filter.return_value.__next__.return_value = MockResponse(
                status_code=200, json_data={"data": []}
            )

            args = SimpleNamespace(sleep_time=5)

            self.s3_matcher_process = mp.Process(target=s3_matcher.run, args=(args,))
            self.s3_matcher_process.start()

            self.varys_client.send(
                example_csv_msg, exchange="inbound.s3", queue_suffix="s3_matcher"
            )
            self.varys_client.send(
                example_fastq_msg, exchange="inbound.s3", queue_suffix="s3_matcher"
            )

            message = self.varys_client.receive(
                exchange="inbound.matched",
                queue_suffix="s3_matcher",
                timeout=30,
            )

            self.assertIsNotNone(message)

            self.varys_client.send(
                example_csv_msg_2, exchange="inbound.s3", queue_suffix="s3_matcher"
            )

            message_2 = self.varys_client.receive(
                exchange="inbound.matched",
                queue_suffix="s3_matcher",
                timeout=30,
            )

            self.assertIsNotNone(message_2)

            message_dict = json.loads(message_2.body)

            self.assertEqual(message_dict["sample_id"], "sample-test")
            self.assertEqual(
                message_dict["artifact"], "mscapetest.sample-test.run-test"
            )
            self.assertEqual(message_dict["run_name"], "run-test")
            self.assertEqual(message_dict["project"], "mscapetest")
            self.assertEqual(message_dict["platform"], "ont")
            self.assertEqual(message_dict["site"], "birm")
            self.assertEqual(message_dict["uploaders"], ["testuser"])
            self.assertEqual(
                message_dict["files"][".csv"]["key"],
                "mscapetest.sample-test.run-test.ont.csv",
            )
            self.assertEqual(
                message_dict["files"][".fastq.gz"]["key"],
                "mscapetest.sample-test.run-test.fastq.gz",
            )
            self.assertTrue(uuid.UUID(message_dict["uuid"], version=4))

    def test_s3_identical_csv(self):
        with patch("roz_scripts.s3_matcher.OnyxClient") as mock_client:
            mock_client.return_value.__enter__.return_value._filter.return_value.__next__.return_value = MockResponse(
                status_code=200, json_data={"data": []}
            )

            args = SimpleNamespace(sleep_time=5)

            self.s3_matcher_process = mp.Process(target=s3_matcher.run, args=(args,))
            self.s3_matcher_process.start()

            self.varys_client.send(
                example_csv_msg, exchange="inbound.s3", queue_suffix="s3_matcher"
            )
            self.varys_client.send(
                example_fastq_msg, exchange="inbound.s3", queue_suffix="s3_matcher"
            )

            message = self.varys_client.receive(
                exchange="inbound.matched",
                queue_suffix="s3_matcher",
                timeout=30,
            )

            self.assertIsNotNone(message)

            self.varys_client.send(
                example_csv_msg, exchange="inbound.s3", queue_suffix="s3_matcher"
            )

            message_2 = self.varys_client.receive(
                exchange="inbound.matched",
                queue_suffix="s3_matcher",
                timeout=30,
            )

            self.assertIsNone(message_2)


class Test_ingest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadedMotoServer()
        self.server.start()

        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

        os.environ["UNIT_TESTING"] = "True"

        self.s3_client = boto3.client("s3", endpoint_url="http://localhost:5000")
        self.s3_client.create_bucket(Bucket="mscapetest-birm-ont-prod")

        with open(TEST_CSV_FILENAME, "w") as f:
            f.write("sample_id,run_name,project,platform,site\n")
            f.write("sample-test,run-test,mscapetest,ont,birm")

        self.s3_client.upload_file(
            TEST_CSV_FILENAME,
            "mscapetest-birm-ont-prod",
            "mscapetest.sample-test.run-test.ont.csv",
        )

        resp = self.s3_client.head_object(
            Bucket="mscapetest-birm-ont-prod",
            Key="mscapetest.sample-test.run-test.ont.csv",
        )

        csv_etag = resp["ETag"]

        example_match_message["files"][".csv"]["etag"] = csv_etag.replace('"', "")
        example_mismatch_match_message["files"][".csv"]["etag"] = csv_etag.replace(
            '"', ""
        )

        config = {
            "version": "0.1",
            "profiles": {
                "roz": {
                    "username": "guest",
                    "password": "guest",
                    "amqp_url": "127.0.0.1",
                    "port": 5672,
                }
            },
        }

        with open(VARYS_CFG_PATH, "w") as f:
            json.dump(config, f, ensure_ascii=False)

        os.environ["VARYS_CFG"] = VARYS_CFG_PATH
        os.environ["S3_MATCHER_LOG"] = ROZ_INGEST_LOG_FILENAME
        os.environ["INGEST_LOG_LEVEL"] = "DEBUG"
        os.environ["ROZ_CONFIG_JSON"] = "config/config.json"
        os.environ["ONYX_ROZ_PASSWORD"] = "password"
        os.environ["ROZ_INGEST_LOG"] = ROZ_INGEST_LOG_FILENAME

        self.varys_client = varys("roz", TEST_MESSAGE_LOG_FILENAME)

    def tearDown(self):
        self.varys_client.close()
        self.server.stop()
        self.ingest_process.kill()

        credentials = pika.PlainCredentials("guest", "guest")

        connection = pika.BlockingConnection(
            pika.ConnectionParameters("localhost", credentials=credentials)
        )
        channel = connection.channel()

        os.remove(TEST_CSV_FILENAME)

        channel.queue_delete(queue="inbound.matched")
        channel.queue_delete(queue="inbound.to_validate.mscapetest")

        connection.close()
        time.sleep(1)

    def test_ingest_successful(self):
        with patch("roz_scripts.ingest.OnyxClient") as mock_client:
            mock_client.return_value.__enter__.return_value._csv_create.return_value.__iter__.return_value = [
                MockResponse(status_code=201, json_data={"data": []}, ok=True)
            ]

            self.ingest_process = mp.Process(target=ingest.main)
            self.ingest_process.start()

            self.varys_client.send(
                example_match_message,
                exchange="inbound.matched",
                queue_suffix="s3_matcher",
            )

            message = self.varys_client.receive(
                exchange="inbound.to_validate.mscapetest",
                queue_suffix="ingest",
                timeout=30,
            )

            self.assertIsNotNone(message)

            message_dict = json.loads(message.body)

            self.assertEqual(message_dict["sample_id"], "sample-test")
            self.assertEqual(
                message_dict["artifact"], "mscapetest.sample-test.run-test"
            )
            self.assertEqual(message_dict["run_name"], "run-test")
            self.assertEqual(message_dict["project"], "mscapetest")
            self.assertEqual(message_dict["platform"], "ont")
            self.assertEqual(message_dict["site"], "birm")
            self.assertEqual(message_dict["uploaders"], ["testuser"])
            self.assertEqual(
                message_dict["files"][".csv"]["key"],
                "mscapetest.sample-test.run-test.ont.csv",
            )
            self.assertTrue(message_dict["validate"])
            self.assertEqual(message_dict["onyx_test_create_errors"], {})
            self.assertEqual(message_dict["onyx_test_status_code"], 201)
            self.assertTrue(message_dict["onyx_test_create_status"])
            self.assertFalse(message_dict["cid"])
            self.assertFalse(message_dict["test_flag"])
            self.assertTrue(uuid.UUID(message_dict["uuid"], version=4))

    def test_name_mismatches(self):
        with patch("roz_scripts.ingest.OnyxClient") as mock_client:
            mock_client.return_value.__enter__.return_value._csv_create.return_value.__iter__.return_value = [
                MockResponse(status_code=201, json_data={"data": []}, ok=True)
            ]

            self.ingest_process = mp.Process(target=ingest.main)
            self.ingest_process.start()

            self.varys_client.send(
                example_mismatch_match_message,
                exchange="inbound.matched",
                queue_suffix="s3_matcher",
            )

            message = self.varys_client.receive(
                exchange="inbound.to_validate.mscapetest",
                queue_suffix="ingest",
                timeout=30,
            )

            self.assertIsNotNone(message)

            message_dict = json.loads(message.body)

            self.assertEqual(message_dict["sample_id"], "sample-test-2")
            self.assertEqual(
                message_dict["artifact"], "mscapetest.sample-test-2.run-test-2"
            )
            self.assertEqual(message_dict["run_name"], "run-test-2")
            self.assertEqual(message_dict["project"], "mscapetest")
            self.assertEqual(message_dict["platform"], "ont")
            self.assertEqual(message_dict["site"], "birm")
            self.assertEqual(message_dict["uploaders"], ["testuser"])
            self.assertEqual(
                message_dict["files"][".csv"]["key"],
                "mscapetest.sample-test.run-test.ont.csv",
            )
            self.assertIn(
                "Field does not match filename",
                message_dict["onyx_test_create_errors"]["sample_id"],
            )
            self.assertIn(
                "Field does not match filename",
                message_dict["onyx_test_create_errors"]["run_name"],
            )
            self.assertFalse(message_dict["validate"])
            self.assertEqual(message_dict["onyx_test_status_code"], 201)
            self.assertTrue(message_dict["onyx_test_create_status"])
            self.assertFalse(message_dict["cid"])
            self.assertFalse(message_dict["test_flag"])
            self.assertTrue(uuid.UUID(message_dict["uuid"], version=4))

    def test_multiline_csv(self):
        with patch("roz_scripts.ingest.OnyxClient") as mock_client:
            mock_client.return_value.__enter__.return_value._csv_create.return_value.__iter__.return_value = [
                MockResponse(status_code=201, json_data={"data": []}, ok=True),
                MockResponse(status_code=201, json_data={"data": []}, ok=True),
            ]

            self.ingest_process = mp.Process(target=ingest.main)
            self.ingest_process.start()

            self.varys_client.send(
                example_match_message,
                exchange="inbound.matched",
                queue_suffix="s3_matcher",
            )

            message = self.varys_client.receive(
                exchange="inbound.to_validate.mscapetest",
                queue_suffix="ingest",
                timeout=30,
            )

            self.assertIsNotNone(message)

            message_dict = json.loads(message.body)

            self.assertIn(
                "Multiline metadata CSVs are not permitted",
                message_dict["onyx_test_create_errors"]["metadata_csv"],
            )
            self.assertFalse(message_dict["onyx_test_create_status"])
            self.assertFalse(message_dict["validate"])

    def test_onyx_create_error_handling(self):
        with patch("roz_scripts.ingest.OnyxClient") as mock_client:
            mock_client.return_value.__enter__.return_value._csv_create.return_value.__iter__.return_value = [
                MockResponse(
                    status_code=400,
                    json_data={
                        "data": [],
                        "messages": {"sample_id": "Test sample_id error handling"},
                    },
                    ok=False,
                )
            ]

            self.ingest_process = mp.Process(target=ingest.main)
            self.ingest_process.start()

            self.varys_client.send(
                example_match_message,
                exchange="inbound.matched",
                queue_suffix="s3_matcher",
            )

            message = self.varys_client.receive(
                exchange="inbound.to_validate.mscapetest",
                queue_suffix="ingest",
                timeout=30,
            )

            self.assertIsNotNone(message)

            message_dict = json.loads(message.body)

            self.assertIn(
                "Test sample_id error handling",
                message_dict["onyx_test_create_errors"]["sample_id"],
            )
            self.assertFalse(message_dict["onyx_test_create_status"])
            self.assertEqual(message_dict["onyx_test_status_code"], 400)
            self.assertFalse(message_dict["validate"])


class Test_mscape_validator(unittest.TestCase):
    def setUp(self):
        self.server = ThreadedMotoServer()
        self.server.start()

        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

        os.environ["UNIT_TESTING"] = "True"

        self.s3_client = boto3.client("s3", endpoint_url="http://localhost:5000")
        self.s3_client.create_bucket(Bucket="mscapetest-birm-ont-prod")
        self.s3_client.create_bucket(Bucket="mscapetest-published-reads")
        self.s3_client.create_bucket(Bucket="mscapetest-published-reports")
        self.s3_client.create_bucket(Bucket="mscapetest-published-taxon-reports")
        self.s3_client.create_bucket(Bucket="mscapetest-published-binned-reads")

        with open(TEST_CSV_FILENAME, "w") as f:
            f.write("sample_id,run_name,project,platform,site\n")
            f.write("sample-test,run-test,mscapetest,ont,birm")

        self.s3_client.upload_file(
            TEST_CSV_FILENAME,
            "mscapetest-birm-ont-prod",
            "mscapetest.sample-test.run-test.ont.csv",
        )

        resp = self.s3_client.head_object(
            Bucket="mscapetest-birm-ont-prod",
            Key="mscapetest.sample-test.run-test.ont.csv",
        )

        csv_etag = resp["ETag"].replace('"', "")

        example_validator_message["files"][".csv"]["etag"] = csv_etag

        config = {
            "version": "0.1",
            "profiles": {
                "roz": {
                    "username": "guest",
                    "password": "guest",
                    "amqp_url": "127.0.0.1",
                    "port": 5672,
                }
            },
        }

        with open(VARYS_CFG_PATH, "w") as f:
            json.dump(config, f, ensure_ascii=False)

        os.environ["VARYS_CFG"] = VARYS_CFG_PATH
        os.environ["S3_MATCHER_LOG"] = ROZ_INGEST_LOG_FILENAME
        os.environ["INGEST_LOG_LEVEL"] = "DEBUG"
        os.environ["ROZ_CONFIG_JSON"] = "config/config.json"
        os.environ["ONYX_ROZ_PASSWORD"] = "password"
        os.environ["ROZ_INGEST_LOG"] = ROZ_INGEST_LOG_FILENAME

        self.varys_client = varys("roz", TEST_MESSAGE_LOG_FILENAME)

    def tearDown(self):
        credentials = pika.PlainCredentials("guest", "guest")

        connection = pika.BlockingConnection(
            pika.ConnectionParameters("localhost", credentials=credentials)
        )
        channel = connection.channel()

        channel.queue_delete(queue="inbound.to_validate.mscapetest")
        channel.queue_delete(queue="inbound.new_artifact.mscape")
        channel.queue_delete(queue="inbound.results.mscape.birm")

        connection.close()

        os.remove(TEST_CSV_FILENAME)

        self.server.stop()
        self.varys_client.close()
        self.validator_process.kill()
        time.sleep(1)

    def test_validator_successful(self):
        with (
            patch("roz_scripts.mscape_ingest_validation.pipeline") as mock_pipeline,
            patch("roz_scripts.mscape_ingest_validation.OnyxClient") as mock_client,
        ):
            mock_pipeline.return_value.execute.return_value = (
                0,
                False,
                "test_stdout",
                "test_stderr",
            )

            mock_pipeline.return_value.cleanup.return_value = (
                0,
                False,
                "test_stdout",
                "test_stderr",
            )
            mock_pipeline.return_value.cmd.return_value = "Hello pytest :)"

            mock_client.return_value.__enter__.return_value._update.return_value = (
                MockResponse(status_code=200)
            )

            mock_client.return_value.__enter__.return_value._csv_create.return_value.__next__.return_value = MockResponse(
                status_code=201, json_data={"data": {"cid": "test_cid"}}
            )

            result_path = os.path.join(DIR, example_validator_message["uuid"])
            preprocess_path = os.path.join(result_path, "preprocess")
            classifications_path = os.path.join(result_path, "classifications")
            pipeline_info_path = os.path.join(result_path, "pipeline_info")
            binned_reads_path = os.path.join(result_path, "reads_by_taxa")

            os.makedirs(preprocess_path, exist_ok=True)
            os.makedirs(classifications_path, exist_ok=True)
            os.makedirs(pipeline_info_path, exist_ok=True)
            os.makedirs(binned_reads_path, exist_ok=True)

            open(
                os.path.join(
                    preprocess_path,
                    f"{example_validator_message['uuid']}.fastp.fastq.gz",
                ),
                "w",
            ).close()
            open(
                os.path.join(classifications_path, "PlusPF.kraken_report.txt"), "w"
            ).close()
            open(os.path.join(binned_reads_path, "reads.286.fastq.gz"), "w").close()
            open(
                os.path.join(
                    result_path, f"{example_validator_message['uuid']}_report.html"
                ),
                "w",
            ).close()

            with open(
                os.path.join(
                    pipeline_info_path,
                    f"execution_trace_{example_validator_message['uuid']}.txt",
                ),
                "w",
            ) as f:
                f.write(example_execution_trace)

            with open(os.path.join(binned_reads_path, "reads_summary.json"), "w") as f:
                json.dump(example_reads_summary, f)

            args = SimpleNamespace(
                logfile=os.path.join(DIR, "mscape_ingest.log"),
                log_level="DEBUG",
                nxf_executable="test",
                nxf_config="test",
                k2_host="test",
                result_dir=DIR,
                n_workers=2,
            )

            self.validator_process = mp.Process(
                target=mscape_ingest_validation.run, args=(args,)
            )

            self.validator_process.start()

            self.varys_client.send(
                example_validator_message,
                exchange="inbound.to_validate.mscapetest",
                queue_suffix="validator",
            )

            new_artifact_message = self.varys_client.receive(
                exchange="inbound.new_artifact.mscape",
                queue_suffix="ingest",
                timeout=30,
            )

            self.assertIsNotNone(new_artifact_message)
            new_artifact_message_dict = json.loads(new_artifact_message.body)

            self.assertEqual(new_artifact_message_dict["cid"], "test_cid")
            self.assertEqual(new_artifact_message_dict["platform"], "ont")
            self.assertEqual(new_artifact_message_dict["site"], "birm")
            self.assertTrue(
                uuid.UUID(new_artifact_message_dict["match_uuid"], version=4)
            )

            detailed_result_message = self.varys_client.receive(
                "inbound.results.mscape.birm", queue_suffix="validator", timeout=30
            )
            self.assertIsNotNone(detailed_result_message)
            detailed_result_message_dict = json.loads(detailed_result_message.body)

            self.assertTrue(uuid.UUID(detailed_result_message_dict["uuid"], version=4))
            self.assertEqual(
                detailed_result_message_dict["artifact"],
                "mscapetest.sample-test.run-test",
            )
            self.assertEqual(detailed_result_message_dict["project"], "mscapetest")
            self.assertEqual(detailed_result_message_dict["site"], "birm")
            self.assertEqual(detailed_result_message_dict["platform"], "ont")
            self.assertEqual(detailed_result_message_dict["cid"], "test_cid")
            self.assertEqual(detailed_result_message_dict["created"], True)
            self.assertEqual(detailed_result_message_dict["ingested"], True)
            self.assertEqual(detailed_result_message_dict["onyx_test_status_code"], 201)
            self.assertEqual(
                detailed_result_message_dict["onyx_test_create_status"], True
            )
            self.assertEqual(detailed_result_message_dict["onyx_status_code"], 201)
            self.assertEqual(detailed_result_message_dict["onyx_create_status"], True)
            self.assertEqual(detailed_result_message_dict["test_flag"], False)
            self.assertEqual(detailed_result_message_dict["ingest_errors"], [])

            published_reads_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-reads"
            )
            self.assertEqual(
                published_reads_contents["Contents"][0]["Key"], "test_cid.fastq.gz"
            )

            published_reports_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-reports"
            )
            self.assertEqual(
                published_reports_contents["Contents"][0]["Key"],
                "test_cid_scylla_report.html",
            )

            published_taxon_reports_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-taxon-reports"
            )
            self.assertEqual(
                published_taxon_reports_contents["Contents"][0]["Key"],
                "test_cid/PlusPF.kraken_report.txt",
            )

            published_binned_reads_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-binned-reads"
            )
            self.assertEqual(
                published_binned_reads_contents["Contents"][0]["Key"],
                "test_cid/286.fastq.gz",
            )

    def test_too_much_human(self):
        with (
            patch("roz_scripts.mscape_ingest_validation.pipeline") as mock_pipeline,
            patch("roz_scripts.mscape_ingest_validation.OnyxClient") as mock_client,
        ):
            mock_pipeline.return_value.execute.return_value = (
                0,
                False,
                "test_stdout",
                "test_stderr",
            )

            mock_pipeline.return_value.cleanup.return_value = (
                0,
                False,
                "test_stdout",
                "test_stderr",
            )
            mock_pipeline.return_value.cmd.return_value = "Hello pytest :)"

            mock_client.return_value.__enter__.return_value._update.return_value = (
                MockResponse(status_code=200)
            )

            mock_client.return_value.__enter__.return_value._csv_create.return_value.__next__.return_value = MockResponse(
                status_code=201, json_data={"data": {"cid": "test_cid"}}
            )

            result_path = os.path.join(DIR, example_validator_message["uuid"])
            preprocess_path = os.path.join(result_path, "preprocess")
            classifications_path = os.path.join(result_path, "classifications")
            pipeline_info_path = os.path.join(result_path, "pipeline_info")
            binned_reads_path = os.path.join(result_path, "reads_by_taxa")

            os.makedirs(preprocess_path, exist_ok=True)
            os.makedirs(classifications_path, exist_ok=True)
            os.makedirs(pipeline_info_path, exist_ok=True)
            os.makedirs(binned_reads_path, exist_ok=True)

            open(
                os.path.join(
                    preprocess_path,
                    f"{example_validator_message['uuid']}.fastp.fastq.gz",
                ),
                "w",
            ).close()
            open(
                os.path.join(classifications_path, "PlusPF.kraken_report.txt"), "w"
            ).close()
            open(
                os.path.join(
                    result_path, f"{example_validator_message['uuid']}_report.html"
                ),
                "w",
            ).close()

            with open(
                os.path.join(
                    pipeline_info_path,
                    f"execution_trace_{example_validator_message['uuid']}.txt",
                ),
                "w",
            ) as f:
                f.write(example_execution_trace_human)

            with open(os.path.join(binned_reads_path, "reads_summary.json"), "w") as f:
                json.dump(example_reads_summary, f)

            args = SimpleNamespace(
                logfile=os.path.join(DIR, "mscape_ingest.log"),
                log_level="DEBUG",
                nxf_executable="test",
                nxf_config="test",
                k2_host="test",
                result_dir=DIR,
                n_workers=2,
            )

            self.validator_process = mp.Process(
                target=mscape_ingest_validation.run, args=(args,)
            )

            self.validator_process.start()

            self.varys_client.send(
                example_validator_message,
                exchange="inbound.to_validate.mscapetest",
                queue_suffix="validator",
            )

            new_artifact_message = self.varys_client.receive(
                exchange="inbound.new_artifact.mscape",
                queue_suffix="ingest",
                timeout=10,
            )

            self.assertIsNone(new_artifact_message)

            detailed_result_message = self.varys_client.receive(
                "inbound.results.mscape.birm", queue_suffix="validator", timeout=30
            )

            self.assertIsNotNone(detailed_result_message)

            detailed_result_message_dict = json.loads(detailed_result_message.body)

            self.assertIn(
                "Human reads detected above rejection threshold, please ensure pre-upload dehumanisation has been performed properly",
                detailed_result_message_dict["ingest_errors"],
            )

            self.assertFalse(detailed_result_message_dict["created"])
            self.assertFalse(detailed_result_message_dict["ingested"])
            self.assertFalse(detailed_result_message_dict["onyx_create_status"])
            self.assertFalse(detailed_result_message_dict["cid"])

            published_reads_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-reads"
            )
            self.assertNotIn("Contents", published_reads_contents.keys())

            published_reports_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-reports"
            )
            self.assertNotIn("Contents", published_reports_contents.keys())

            published_taxon_reports_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-taxon-reports"
            )
            self.assertNotIn("Contents", published_taxon_reports_contents.keys())

            published_binned_reads_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-binned-reads"
            )
            self.assertNotIn("Contents", published_binned_reads_contents.keys())

    def test_successful_test(self):
        with (
            patch("roz_scripts.mscape_ingest_validation.pipeline") as mock_pipeline,
            patch("roz_scripts.mscape_ingest_validation.OnyxClient") as mock_client,
        ):
            mock_pipeline.return_value.execute.return_value = (
                0,
                False,
                "test_stdout",
                "test_stderr",
            )

            mock_pipeline.return_value.cleanup.return_value = (
                0,
                False,
                "test_stdout",
                "test_stderr",
            )
            mock_pipeline.return_value.cmd.return_value = "Hello pytest :)"

            mock_client.return_value.__enter__.return_value._update.return_value = (
                MockResponse(status_code=200)
            )

            mock_client.return_value.__enter__.return_value._csv_create.return_value.__next__.return_value = MockResponse(
                status_code=201, json_data={"data": {"cid": "test_cid"}}
            )

            result_path = os.path.join(DIR, example_validator_message["uuid"])
            preprocess_path = os.path.join(result_path, "preprocess")
            classifications_path = os.path.join(result_path, "classifications")
            pipeline_info_path = os.path.join(result_path, "pipeline_info")
            binned_reads_path = os.path.join(result_path, "reads_by_taxa")

            os.makedirs(preprocess_path, exist_ok=True)
            os.makedirs(classifications_path, exist_ok=True)
            os.makedirs(pipeline_info_path, exist_ok=True)
            os.makedirs(binned_reads_path, exist_ok=True)

            open(
                os.path.join(
                    preprocess_path,
                    f"{example_validator_message['uuid']}.fastp.fastq.gz",
                ),
                "w",
            ).close()
            open(
                os.path.join(classifications_path, "PlusPF.kraken_report.txt"), "w"
            ).close()
            open(
                os.path.join(
                    result_path, f"{example_validator_message['uuid']}_report.html"
                ),
                "w",
            ).close()

            with open(
                os.path.join(
                    pipeline_info_path,
                    f"execution_trace_{example_validator_message['uuid']}.txt",
                ),
                "w",
            ) as f:
                f.write(example_execution_trace)

            with open(os.path.join(binned_reads_path, "reads_summary.json"), "w") as f:
                json.dump(example_reads_summary, f)

            args = SimpleNamespace(
                logfile=os.path.join(DIR, "mscape_ingest.log"),
                log_level="DEBUG",
                nxf_executable="test",
                nxf_config="test",
                k2_host="test",
                result_dir=DIR,
                n_workers=2,
            )

            self.validator_process = mp.Process(
                target=mscape_ingest_validation.run, args=(args,)
            )

            self.validator_process.start()

            self.varys_client.send(
                example_test_validator_message,
                exchange="inbound.to_validate.mscapetest",
                queue_suffix="validator",
            )

            new_artifact_message = self.varys_client.receive(
                exchange="inbound.new_artifact.mscape",
                queue_suffix="ingest",
                timeout=10,
            )

            self.assertIsNone(new_artifact_message)

            detailed_result_message = self.varys_client.receive(
                "inbound.results.mscape.birm", queue_suffix="validator", timeout=30
            )

            self.assertIsNotNone(detailed_result_message)

            detailed_result_message_dict = json.loads(detailed_result_message.body)

            self.assertFalse(detailed_result_message_dict["created"])
            self.assertFalse(detailed_result_message_dict["ingested"])
            self.assertFalse(detailed_result_message_dict["onyx_create_status"])
            self.assertFalse(detailed_result_message_dict["cid"])
            self.assertTrue(detailed_result_message_dict["test_ingest_result"])
            self.assertFalse(detailed_result_message_dict["ingest_errors"])

            published_reads_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-reads"
            )
            self.assertNotIn("Contents", published_reads_contents.keys())

            published_reports_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-reports"
            )
            self.assertNotIn("Contents", published_reports_contents.keys())

            published_taxon_reports_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-taxon-reports"
            )
            self.assertNotIn("Contents", published_taxon_reports_contents.keys())

            published_binned_reads_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-binned-reads"
            )
            self.assertNotIn("Contents", published_binned_reads_contents.keys())

    def test_onyx_fail(self):
        with (
            patch("roz_scripts.mscape_ingest_validation.pipeline") as mock_pipeline,
            patch("roz_scripts.mscape_ingest_validation.OnyxClient") as mock_client,
        ):
            mock_pipeline.return_value.execute.return_value = (
                0,
                False,
                "test_stdout",
                "test_stderr",
            )

            mock_pipeline.return_value.cleanup.return_value = (
                0,
                False,
                "test_stdout",
                "test_stderr",
            )
            mock_pipeline.return_value.cmd.return_value = "Hello pytest :)"

            mock_client.return_value.__enter__.return_value._update.return_value = (
                MockResponse(status_code=400, ok=False)
            )

            mock_client.return_value.__enter__.return_value._csv_create.return_value.__next__.return_value = MockResponse(
                status_code=400,
                json_data={
                    "data": [],
                    "messages": {"sample_id": "Test sample_id error handling"},
                },
                ok=False,
            )

            result_path = os.path.join(DIR, example_validator_message["uuid"])
            preprocess_path = os.path.join(result_path, "preprocess")
            classifications_path = os.path.join(result_path, "classifications")
            pipeline_info_path = os.path.join(result_path, "pipeline_info")
            binned_reads_path = os.path.join(result_path, "reads_by_taxa")

            os.makedirs(preprocess_path, exist_ok=True)
            os.makedirs(classifications_path, exist_ok=True)
            os.makedirs(pipeline_info_path, exist_ok=True)
            os.makedirs(binned_reads_path, exist_ok=True)

            open(
                os.path.join(
                    preprocess_path,
                    f"{example_validator_message['uuid']}.fastp.fastq.gz",
                ),
                "w",
            ).close()
            open(
                os.path.join(classifications_path, "PlusPF.kraken_report.txt"), "w"
            ).close()
            open(
                os.path.join(
                    result_path, f"{example_validator_message['uuid']}_report.html"
                ),
                "w",
            ).close()

            with open(
                os.path.join(
                    pipeline_info_path,
                    f"execution_trace_{example_validator_message['uuid']}.txt",
                ),
                "w",
            ) as f:
                f.write(example_execution_trace)

            with open(os.path.join(binned_reads_path, "reads_summary.json"), "w") as f:
                json.dump(example_reads_summary, f)

            args = SimpleNamespace(
                logfile=os.path.join(DIR, "mscape_ingest.log"),
                log_level="DEBUG",
                nxf_executable="test",
                nxf_config="test",
                k2_host="test",
                result_dir=DIR,
                n_workers=2,
            )

            self.validator_process = mp.Process(
                target=mscape_ingest_validation.run, args=(args,)
            )

            self.validator_process.start()

            self.varys_client.send(
                example_validator_message,
                exchange="inbound.to_validate.mscapetest",
                queue_suffix="validator",
            )

            new_artifact_message = self.varys_client.receive(
                exchange="inbound.new_artifact.mscape",
                queue_suffix="ingest",
                timeout=10,
            )

            self.assertIsNone(new_artifact_message)

            detailed_result_message = self.varys_client.receive(
                "inbound.results.mscape.birm", queue_suffix="validator", timeout=30
            )

            self.assertIsNotNone(detailed_result_message)

            detailed_result_message_dict = json.loads(detailed_result_message.body)

            self.assertFalse(detailed_result_message_dict["created"])
            self.assertFalse(detailed_result_message_dict["ingested"])
            self.assertFalse(detailed_result_message_dict["onyx_create_status"])
            self.assertFalse(detailed_result_message_dict["cid"])
            self.assertFalse(detailed_result_message_dict["test_ingest_result"])

            self.assertIn(
                "Test sample_id error handling",
                detailed_result_message_dict["onyx_errors"]["sample_id"],
            )
            self.assertFalse(detailed_result_message_dict["onyx_create_status"])
            self.assertEqual(detailed_result_message_dict["onyx_status_code"], 400)

            published_reads_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-reads"
            )
            self.assertNotIn("Contents", published_reads_contents.keys())

            published_reports_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-reports"
            )
            self.assertNotIn("Contents", published_reports_contents.keys())

            published_taxon_reports_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-taxon-reports"
            )
            self.assertNotIn("Contents", published_taxon_reports_contents.keys())

            published_binned_reads_contents = self.s3_client.list_objects(
                Bucket="mscapetest-published-binned-reads"
            )
            self.assertNotIn("Contents", published_binned_reads_contents.keys())
