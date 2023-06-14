import csv
import os
import sys
import time
import json
import copy

from onyx import Session as onyx_session

from roz import varys


def handle_status_code(status_code):
    if status_code == 422:
        return (False, "validation_failure")
    elif status_code == 403:
        return (False, "perm_failure")
    elif status_code == 201:
        return (True, "success")
    else:
        return (False, "unknown")


def main():
    for i in (
        "ONYX_ROZ_PASSWORD",
        "ROZ_INGEST_LOG",
    ):
        if not os.getenv(i):
            print(f"The environmental variable '{i}' has not been set", file=sys.stderr)
            sys.exit(3)

    # Setup producer / consumer
    log = varys.init_logger(
        "roz_ingest", os.getenv("ROZ_INGEST_LOG"), os.getenv("ROZ_LOG_LEVEL")
    )

    varys_client = varys.varys(
        profile="roz",
        in_exchange="inbound.matched",
        out_exchange="inbound.to_validate",
        logfile=os.getenv("ROZ_INGEST_LOG"),
        log_level=os.getenv("ROZ_LOG_LEVEL"),
        queue_suffix="ingest",
    )

    ingest_payload_template = {
        "mid": "",
        "artifact": "",
        "sample_id": "",
        "run_name": "",
        "project": "",
        "platform": "",
        "ingest_timestamp": "",
        "cid": False,
        "site": "",
        "created": False,
        "ingested": False,
        "files": {},  # Dict
        "local_paths": {},  # Dict
        "onyx_test_status_code": False,
        "onyx_test_create_errors": {},  # Dict
        "onyx_test_create_status": False,
        "onyx_status_code": False,
        "onyx_errors": {},  # Dict
        "onyx_create_status": False,
        "ingest_errors": {},
    }

    while True:
        payload = copy.deepcopy(ingest_payload_template)

        message = varys_client.receive()

        matched_message = json.loads(message.body)

        # TODO: make this an actual unique MID
        payload["mid"] = message.basic_deliver.delivery_tag

        # Not sure how to fully generalise this, the idea is to have a csv as the only file that will always exist, so I guess this is okay?
        # CSV file must always be called '.csv' though
        with onyx_session() as client:
            log.info(
                f"Received match for artifact: {matched_message['artifact']}, now attempting to test_create record in Onyx"
            )

            try:
                # Test create from the metadata CSV
                response_generator = client.csv_create(
                    matched_message["project"],
                    csv_path=matched_message["local_paths"][
                        ".csv"
                    ],  # I don't like having a hardcoded metadata file name like this but hypothetically
                    test=True,  # we should always have a metadata CSV
                )
            except Exception as e:
                log.error(
                    f"Onxy test csv create failed for artifact: {matched_message['artifact']} due to client error: {e}"
                )
                continue

            to_test = False
            multiline_csv = False

            for response in response_generator:
                if to_test:
                    log.info(
                        f"Metadata CSV for artifact {payload['artifact']} contains more than one record, metadata CSVs should only ever contain a single record"
                    )
                    multiline_csv = True
                    break
                else:
                    to_test = response

        if not multiline_csv:
            with open(matched_message["local_paths"][".csv"], "rt") as csv_fh:
                reader = csv.DictReader(csv_fh, delimiter=",")

                metadata = next(reader)

                name_matches = {
                    x: metadata[x] == matched_message[x]
                    for x in ("sample_id", "run_name")
                }

                for k, v in name_matches.items():
                    if not v:
                        if payload["onyx_test_create_errors"].get(k):
                            payload["onyx_test_create_errors"][k].append(
                                "Field does not match filename"
                            )
                        else:
                            payload["onyx_test_create_errors"][k] = [
                                "Field does not match filename"
                            ]

                if not all(name_matches.keys()):
                    payload["artifact"] = matched_message["artifact"]
                    payload["sample_id"] = matched_message["sample_id"]
                    payload["run_name"] = matched_message["run_name"]
                    payload["project"] = matched_message["project"]
                    payload["platform"] = matched_message["platform"]
                    payload["ingest_timestamp"] = time.time_ns()
                    payload["site"] = matched_message["site"]
                    payload["files"] = matched_message["files"]
                    payload["local_paths"] = matched_message["local_paths"]

                    varys_client.send(payload)
                    continue

        if multiline_csv:
            if payload["onyx_test_create_errors"].get("metadata_csv"):
                payload["onyx_test_create_errors"]["metadata_csv"].append(
                    "Multiline metadata CSVs are not permitted"
                )
            else:
                payload["onyx_test_create_errors"]["metadata_csv"] = [
                    "Multiline metadata CSVs are not permitted"
                ]

        else:
            status, reason = handle_status_code(to_test.status_code)

            log.info(
                f"Received Onyx test create response for artifact: {matched_message['artifact']}"
            )

            payload["onyx_test_create_status"] = status
            payload["onyx_test_status_code"] = to_test.status_code

            if to_test.json().get("messages"):
                for field, messages in to_test.json()["messages"].items():
                    if payload["onyx_test_create_errors"].get(field):
                        payload["onyx_test_create_errors"][field].extend(messages)
                    else:
                        payload["onyx_test_create_errors"][field] = messages

            if not status:
                if reason == "unknown":
                    log.error(
                        f"Onyx test create returned an unknown status code: {to_test.status_code} for artifact: {matched_message['artifact']}"
                    )
                    continue

                elif reason == "perm_failure":
                    log.error(
                        f"Onyx test create for artifact: {matched_message['artifact']} due to Onyx permissions failure"
                    )
                    continue

            elif reason == "success":
                log.info(
                    f"Onyx test create success for artifact: {matched_message['artifact']}"
                )
                if to_test.json()["data"]["cid"]:
                    log.error(
                        f"Onyx appears to have assigned a CID ({response['data']['cid']}) to artifact: {matched_message['artifact']}. This should NOT happen in any circumstance."
                    )
                    continue

        payload["artifact"] = matched_message["artifact"]
        payload["sample_id"] = matched_message["sample_id"]
        payload["run_name"] = matched_message["run_name"]
        payload["project"] = matched_message["project"]
        payload["platform"] = matched_message["platform"]
        payload["ingest_timestamp"] = time.time_ns()
        payload["site"] = matched_message["site"]
        payload["files"] = matched_message["files"]
        payload["local_paths"] = matched_message["local_paths"]

        varys_client.send(payload)


if __name__ == "__main__":
    main()
