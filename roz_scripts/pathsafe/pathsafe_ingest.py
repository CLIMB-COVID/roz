import os
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
import json
import copy
import argparse
import logging
import csv
import requests
import time
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED


from roz_scripts.utils.utils import (
    onyx_submission,
    onyx_unsuppress,
    onyx_update,
    pipeline,
)
from varys.utils import init_logger
from varys import varys
from onyx import OnyxClient


def assembly_to_s3(
    payload: dict,
    s3_client: boto3.client,
    result_path: str,
    log: logging.getLogger,
) -> tuple[bool, dict]:
    """Function to upload raw reads to long-term storage bucket and add the fastq_1 and fastq_2 fields to the Onyx record

    Args:
        payload (dict): Payload dict for the record to update
        s3_client (boto3.client): Boto3 client object for S3
        result_path (str): Path to the results directory
        log (logging.getLogger): Logger object

    Returns:
        tuple[bool, dict]: Tuple containing a bool indicating whether the upload failed and the updated payload dict
    """

    s3_fail = False

    assembly_path = os.path.join(
        result_path, f"assembly/{payload['uuid']}.result.fasta"
    )

    try:
        s3_client.upload_file(
            assembly_path,
            "pathsafetest-new-assembly",
            f"{payload['cid']}.assembly.fasta",
        )

        payload["presigned_url"] = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": "pathsafetest-new-assembly",
                "Key": f"{payload['cid']}.assembly.fasta",
            },
            ExpiresIn=86400,
        )

    except ClientError as e:
        log.error(
            f"Failed to upload assembly to long-term storage bucket for UUID: {payload['uuid']} with CID: {payload['cid']} due to client error: {e}"
        )
        payload["ingest_errors"].append(f"Failed to upload assembly to storage bucket")
        s3_fail = True

    if not s3_fail:
        update_fail, payload = onyx_update(
            payload=payload,
            fields={
                "assembly": f"s3://pathsafetest-new-assembly/{payload['cid']}.assembly.fasta",
            },
            log=log,
        )

        if update_fail:
            s3_fail = True

    return (s3_fail, payload)


def pathogenwatch_submission(
    payload: dict, log: logging.getLogger
) -> tuple[bool, dict]:
    """Function to submit a genome to pathogenwatch

    Args:
        payload (dict): Payload dict for the record to update
        log (logging.getLogger): Logger object
        s3_client (boto3.client): Boto3 client object for S3

    Returns:
        tuple[bool, dict]: Tuple containing a bool indicating whether the submission failed and the updated payload dict
    """
    pathogenwatch_fail = False

    with OnyxClient(env_password=True) as client:
        record = client.get(
            "pathsafetest",
            payload["cid"],
            scope=["admin"],
        )

        ignore_fields = ["suppressed", "sample_id", "run_name"]

        fields = {k: v for k, v in record.items() if v and k not in ignore_fields}

        body = {
            "url": payload["presigned_url"],
            "collectionId": 41,
            "metadata": fields,
        }

        headers = {"X-API-Key": os.getenv("PATHOGENWATCH_API_KEY")}

        endpoint_url = os.getenv("PATHOGENWATCH_ENDPOINT_URL")

        r = requests.post(url=endpoint_url, headers=headers, json=body)

        if r.status_code != 201:
            log.error(
                f"Pathogenwatch submission failed for UUID: {payload['uuid']} with CID: {payload['cid']} due to error: {r.text}"
            )
            payload["ingest_errors"].append(
                f"Pathogenwatch submission failed with status code: {r.status_code}, due to error: {r.text}"
            )
            pathogenwatch_fail = True

        update_fail, payload = onyx_update(
            payload=payload, fields={"pathogenwatch_uuid": r.json()["id"]}, log=log
        )

    return (pathogenwatch_fail, payload)


def execute_assembly_pipeline(
    payload: dict,
    args: argparse.Namespace,
    log: logging.getLogger,
    ingest_pipe: pipeline,
) -> tuple[int, bool, str, str]:
    """Execute the validation pipeline for a given artifact

    Args:
        payload (dict): The payload dict for the current artifact
        args (argparse.Namespace): The command line arguments object
        log (logging.getLogger): The logger object
        ingest_pipe (pipeline): The instance of the ingest pipeline (see pipeline class)

    Returns:
        tuple[int, bool, str, str]: A tuple containing the return code, a bool indicating whether the pipeline timed out, stdout and stderr
    """

    parameters = {
        "out_dir": args.result_dir,
        "sample_uuid": payload["uuid"],
        "fastq_1": payload["files"][".1.fastq.gz"]["uri"],
        "fastq_2": payload["files"][".2.fastq.gz"]["uri"],
    }

    log.info(f"Submitted ingest pipeline for UUID: {payload['uuid']}'")

    return ingest_pipe.execute(params=parameters)


def ret_0_parser(
    log: logging.getLogger,
    payload: dict,
    result_path: str,
    ingest_fail: bool = False,
) -> tuple[bool, dict]:
    """Function to parse the execution trace of a Nextflow pipeline run to determine whether any of the processes failed.

    Args:
        log (logging.getLogger): Logger object
        payload (dict): Payload dictionary
        result_path (str): Path to the results directory
        ingest_fail (bool): Boolean to indicate whether the ingest has failed up to this point (default: False)

    Returns:
        tuple[bool, dict]: Tuple containing the ingest fail boolean and the payload dictionary
    """

    try:
        with open(
            os.path.join(
                result_path,
                "pipeline_info",
                f"execution_trace_{payload['uuid']}.txt",
            )
        ) as trace_fh:
            reader = csv.DictReader(trace_fh, delimiter="\t")

            trace_dict = {}
            for process in reader:
                trace_dict[process["name"].split(":")[-1]] = process

    except Exception as e:
        log.error(
            f"Could not open pipeline trace for UUID: {payload['uuid']} despite NXF exit code 0 due to error: {e}"
        )
        payload["ingest_errors"].append("couldn't open nxf ingest pipeline trace")
        ingest_fail = True

    for process, trace in trace_dict.items():
        if trace["exit"] != "0":
            payload["ingest_errors"].append(
                f"MScape validation pipeline (Scylla) failed in process {process} with exit code {trace['exit']} and status {trace['status']}"
            )
            ingest_fail = True

    return (ingest_fail, payload)


def validate(
    message,
    args: argparse.Namespace,
    log: logging.getLogger,
    ingest_pipe: pipeline,
    s3_client: boto3.client,
    varys_client: varys,
):
    to_validate = json.loads(message.body)

    payload = copy.deepcopy(to_validate)

    # This client is purely for pathsafe, ignore all other messages
    if to_validate["project"] != "pathsafetest":
        log.info(
            f"Ignoring file set with UUID: {to_validate['uuid']} due non-pathsafe project ID"
        )
        return False

    if not to_validate["onyx_test_create_status"] or not to_validate["validate"]:
        varys_client.send(
            message=payload,
            exchange=f"inbound.results.pathsafe.{to_validate['site']}",
            queue_suffix="validator",
        )
        return False

    rc, timeout, stdout, stderr = execute_assembly_pipeline(
        payload=payload, args=args, log=log, ingest_pipe=ingest_pipe
    )

    if not timeout and ingest_pipe.cmd:
        log.info(
            f"Execution of pipeline for UUID: {payload['uuid']} complete. Command was: {ingest_pipe.cmd}"
        )

    if timeout:
        log.error(f"Pipeline execution timed out for message id: {payload['uuid']}")
        payload["ingest_errors"].append("Validation pipeline timeout")
        log.info(f"Sending validation result for UUID: {payload['uuid']}")
        varys_client.send(
            message=payload,
            exchange=f"inbound.results.pathsafe.{to_validate['site']}",
            queue_suffix="validator",
        )
        ingest_pipe.cleanup(stdout=stdout)
        return False

    result_path = os.path.join(args.result_dir.resolve(), payload["uuid"])

    if not os.path.exists(result_path):
        os.makedirs(result_path)

    with open(os.path.join(result_path, "nextflow.stdout"), "wt") as out_fh, open(
        os.path.join(result_path, "nextflow.stderr"), "wt"
    ) as err_fh:
        out_fh.write(stdout)
        err_fh.write(stderr)

    if rc != 0:
        log.error(
            f"Validation pipeline exited with non-0 exit code: {rc} for UUID: {payload['uuid']}"
        )
        payload["ingest_errors"].append(
            f"Validation pipeline exited with non-0 exit code: {rc}"
        )
        varys_client.send(
            message=payload,
            exchange=f"inbound.results.pathsafe.{to_validate['site']}",
            queue_suffix="validator",
        )
        ingest_pipe.cleanup(stdout=stdout)
        return False

    ingest_fail, payload = ret_0_parser(
        log=log,
        payload=payload,
        result_path=result_path,
    )

    if ingest_fail:
        varys_client.send(
            message=payload,
            exchange=f"inbound.results.pathsafe.{to_validate['site']}",
            queue_suffix="validator",
        )
        ingest_pipe.cleanup(stdout=stdout)
        return False

    submission_fail, payload = onyx_submission(log=log, payload=payload)

    if submission_fail:
        log.error(
            f"Submission to Onyx failed for UUID: {payload['uuid']}, sending result"
        )
        varys_client.send(
            message=payload,
            exchange=f"inbound.results.pathsafe.{to_validate['site']}",
            queue_suffix="validator",
        )
        ingest_pipe.cleanup(stdout=stdout)
        return False

    s3_fail, payload = assembly_to_s3(
        payload=payload,
        s3_client=s3_client,
        result_path=result_path,
        log=log,
    )

    if s3_fail:
        log.error(
            f"Failed to upload assembly to long-term storage bucket for UUID: {payload['uuid']}, sending result"
        )
        varys_client.send(
            message=payload,
            exchange=f"inbound.results.pathsafe.{to_validate['site']}",
            queue_suffix="validator",
        )
        ingest_pipe.cleanup(stdout=stdout)
        return False

    pathogenwatch_fail, payload = pathogenwatch_submission(
        payload=payload,
        log=log,
    )

    if pathogenwatch_fail:
        log.error(
            f"Pathogenwatch submission failed for UUID: {payload['uuid']}, sending result"
        )
        varys_client.send(
            message=payload,
            exchange=f"inbound.results.pathsafe.{to_validate['site']}",
            queue_suffix="validator",
        )
        ingest_pipe.cleanup(stdout=stdout)
        return False

    unsuppress_fail, payload = onyx_unsuppress(payload=payload, log=log)

    if unsuppress_fail:
        log.error(
            f"Failed to unsuppress Onyx record for UUID: {payload['uuid']}, sending result"
        )
        varys_client.send(
            message=payload,
            exchange=f"inbound.results.pathsafe.{to_validate['site']}",
            queue_suffix="validator",
        )
        ingest_pipe.cleanup(stdout=stdout)
        return False

    payload["ingested"] = True

    new_artifact_payload = {
        "ingest_timestamp": time.time_ns(),
        "cid": payload["cid"],
        "site": payload["site"],
        "match_uuid": payload["uuid"],
    }

    varys_client.send(
        message=new_artifact_payload,
        exchange="inbound.new_artifact.pathsafe",
        queue_suffix="validator",
    )

    varys_client.send(
        message=payload,
        exchange=f"inbound.results.pathsafe.{to_validate['site']}",
        queue_suffix="validator",
    )

    (
        cleanup_status,
        cleanup_timeout,
        cleanup_stdout,
        cleanup_stderr,
    ) = ingest_pipe.cleanup(stdout=stdout)

    if cleanup_timeout:
        log.error(
            f"Cleanup of pipeline for UUID: {payload['uuid']} timed out. Stdout: {cleanup_stdout}, Stderr: {cleanup_stderr}"
        )

    if cleanup_status != 0:
        log.error(
            f"Cleanup of pipeline for UUID: {payload['uuid']} failed with exit code: {cleanup_status}, Stdout: {cleanup_stdout}, Stderr: {cleanup_stderr}"
        )

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logfile", type=Path, required=True, help="Path to logfile")
    parser.add_argument(
        "--log_level",
        type=str,
        help="Log level for logger object",
        choices=["NOTSET", "INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"],
        default="DEBUG",
    )
    parser.add_argument(
        "--result_dir", type=Path, required=True, help="Path to store results"
    )
    parser.add_argument(
        "--nxf_config", type=Path, required=False, help="Path to nxf config file"
    )
    parser.add_argument(
        "--nxf_executable", type=Path, required=False, default="nextflow"
    )
    parser.add_argument(
        "--n_workers",
        type=int,
        default=5,
        help="Number of workers to use for concurrent validation",
    )
    args = parser.parse_args()

    log = init_logger("pathsafe.ingest", args.logfile, args.log_level)

    varys_client = varys(
        profile="roz",
        logfile=args.logfile,
        log_level=args.log_level,
    )

    validation_payload_template = {
        "uuid": "",
        "artifact": "",
        "project": "",
        "ingest_timestamp": "",
        "cid": False,
        "site": "",
        "created": False,
        "ingested": False,
        "onyx_test_status_code": False,
        "onyx_test_create_errors": {},  # Dict
        "onyx_test_create_status": False,
        "onyx_status_code": False,
        "onyx_errors": {},  # Dict
        "onyx_create_status": False,
        "ingest_errors": [],  # List,
        "test_flag": True,  # Add this throughout
        "test_ingest_result": False,
    }

    ingest_pipe = pipeline(
        pipe="CLIMB-TRE/path-safe_assembler",
        profile="docker",
        config=args.nxf_config,
        nxf_executable=args.nxf_executable,
    )

    s3_client = boto3.client(
        "s3",
        endpoint_url="https://s3.climb.ac.uk",
        aws_access_key_id=os.getenv("ROZ_AWS_ACCESS"),
        aws_secret_access_key=os.getenv("ROZ_AWS_SECRET"),
    )

    max_concurrent = args.n_workers  # how many futures to use at most
    pending = set()  # currently running futures

    with ProcessPoolExecutor(max_workers=args.n_workers) as executor:
        while True:
            # Don't continue until there is a free worker
            while len(pending) >= max_concurrent:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)

            message = varys_client.receive(
                exchange="inbound.to_validate.pathsafetest",
                queue_suffix="validator",
            )

            pending.add(
                executor.submit(
                    validate,
                    kwargs={
                        "message": message,
                        "args": args,
                        "log": log,
                        "ingest_pipe": ingest_pipe,
                        "s3_client": s3_client,
                        "varys_client": varys_client,
                    },
                )
            )


if __name__ == "__main__":
    main()
