#!/usr/bin/env python

import sys
import json
import queue
import multiprocessing as mp
import os

import roz.varys

from roz.util import validate_triplet, get_env_variables, validation_tuple


class worker_pool_handler:
    def __init__(
        self,
        roz_config,
        pathogen_code,
        env_vars,
        max_retries,
        logger,
        outbound_queue,
        workers,
    ):
        self._max_retries = max_retries
        self._roz_config = roz_config
        self._pathogen_code = pathogen_code
        self._env_vars = env_vars
        self._log = logger
        self._out_queue = outbound_queue
        self.worker_pool = mp.Pool(processes=workers)

        self._log.info(f"Successfully initialised worker pool with {workers} workers")

    def submit_job(self, validation_tuple):
        self._log.debug(
            f"Submitting validation triplet {validation_tuple} to worker pool"
        )
        self.worker_pool.apply_async(
            func=validate_triplet,
            args=(
                self._roz_config["configs"][self._pathogen_code],
                self._env_vars,
                validation_tuple,
                self._log,
            ),
            callback=self.callback,
            error_callback=self.error_callback,
        )

    def callback(self, validation_tuple):
        if validation_tuple.success:
            self._log.info(
                f"Successfully validated artifact: {validation_tuple.artifact}"
            )
            if all(
                validation_tuple.payload["validation"][file]["result"] == True
                for file in ("csv", "fasta", "bam")
            ):
                validation_tuple.payload["triplet_result"] = True
            else:
                validation_tuple.payload["triplet_result"] = False

            self._log.info(
                f"Sending validation result for artifact {validation_tuple.artifact}"
            )
            self._out_queue.put(validation_tuple.payload)
        else:
            if validation_tuple.attempts >= self._max_retries:
                self._log.error(
                    f"Unable to successfully process file triplet for artifact: {validation_tuple.artifact} after {self._max_retries} unsuccessful attempts"
                )
            else:
                self._log.error(
                    f"Unable to successfully process file triplet for artifact: {validation_tuple.artifact} with error: {validation_tuple.exception}, automatically retrying"
                )
                self.submit_job(validation_tuple)

    def error_callback(self, exception):
        self._log.error(f"Worker failed with unhandled exception {exception}")


def run(args):

    env_vars = get_env_variables()

    # TODO MAKE THIS LESS SHIT
    try:
        with open(env_vars.json_config, "rt") as validation_cfg_fh:
            validation_config = json.load(validation_cfg_fh)
    except:
        log.error(
            "ROZ configuration JSON could not be parsed, ensure it is valid JSON and restart"
        )
        sys.exit(2)

    varys_client = roz.varys.Varys(
        profile="roz_admin",
        in_exchange="inbound.matched",
        out_exchange="inbound.validated",
        logfile=env_vars.logfile,
        log_level=env_vars.log_level,
        queue_suffix="roz_client",
    )

    log = roz.varys.init_logger("roz_client", env_vars.logfile, env_vars.log_level)

    worker_pool = worker_pool_handler(
        roz_config=validation_config,
        pathogen_code=args.pathogen_code,
        env_vars=env_vars,
        max_retries=args.max_retries,
        logger=log,
        outbound_queue=varys_client.__out_queue,
        workers=args.workers,
    )

    while True:
        triplet_message = varys_client.receive()

        payload = json.loads(triplet_message.body)

        to_validate = validation_tuple(
            payload["artifact"],
            False,
            payload,
            0,
            "",
        )

        log.info(
            f"Received message # {triplet_message.basic_deliver.delivery_tag}, attempting to validate file triplet for artifact {to_validate.artifact}"
        )

        try:
            worker_pool.submit_job(to_validate)
        except Exception as e:
            log.error(f"Unable to submit job to worker pool with error: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pathogen-code", required=True)
    parser.add_argument("--inbound-profile", required=True)
    parser.add_argument("--outbound-profile", required=True)
    parser.add_argument("--workers", default=5, type=int)
    # parser.add_argument("--log-file", required=True)
    parser.add_argument("--max-retries", default=3)
    args = parser.parse_args()

    run(args)


if __name__ == "__main__":
    main()
