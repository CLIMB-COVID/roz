from cmath import e
import queue
from varys import producer, consumer, configurator, init_logger
from queue import Queue
import hashlib
import os
import time
import json
import copy

def hash_file(filepath, blocksize=2 ** 20):
    m = hashlib.md5()
    with open(filepath, "rb") as f:
        while True:
            buf = f.read(blocksize)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest()

def get_already_matched_triplets(configuration):
    triplet_queue = queue.Queue()

    matched_consumer = consumer(triplet_queue, configuration, os.devnull, "CRITICAL", "first").start()

    previous_messages = []
    
    out_dict = {}

    while True:
        try:
            message = triplet_queue.get(timeout=0.5)
            previous_messages.append(message)
        except queue.Empty:
            break
    
    for message in previous_messages:
        payload = json.loads(message.body)
        artifact_record = {"csv": payload["files"]["csv"]["hash"], "fasta": payload["files"]["fasta"]["hash"], "bam": payload["files"]["bam"]["hash"]}
        out_dict[payload["artifact"]] = artifact_record
    
    return out_dict

def payload_parser(payload):
    pass

def directory_scanner(path, old_files):
    found_files = set()

    for file in os.listdir(path):
        fullpath=os.path.join(path, file)
        if fullpath in old_files:
            continue
        current_size = os.path.getsize(fullpath)
        time.sleep(0.5)
        if current_size == os.path.getsize(fullpath):
            if os.path.isfile(fullpath):
                found_files.add(fullpath)
        
    new_files = found_files.difference(old_files)
    return new_files

def generate_payload(artifact, file_triplet, uploader_code, spec_version=1):
    if spec_version == 1:
        ts = time.time_ns()
        payload = {"payload_version": 1, "uploader": uploader_code, "match_timestamp": ts, "artifact": artifact, "files": { "csv": file_triplet["csv"], "fasta": file_triplet["fasta"], "bam": file_triplet["bam"] } }    
    else:
        #TODO HANDLE IT
        pass
    
    return payload

log = init_logger("trip_match_client", os.getenv("ROZ_MATCHER_LOG"), "DEBUG")

file_triplet_cfg = configurator("triplet_matcher", os.getenv("ROZ_PROFILE_CFG"))

file_trip_queue = Queue()

file_triplet_producer = producer(file_trip_queue, file_triplet_cfg, os.getenv("ROZ_MATCHER_LOG_PATH")).start()

log.info("Generating dict of already matched file triplets")
previously_matched = get_already_matched_triplets(file_triplet_cfg)
log.info("Dict of already matched triplets generated successfully")

existing_files = set()

unmatched_artifacts = {}

uploader_code = "BIRM"

while True:
    new_files = directory_scanner(os.getenv("ROZ_INBOUND_PATH"), existing_files)
    existing_files = existing_files.union(new_files)

    if not new_files:
        time.sleep(30)
        continue

    for new_file in new_files:
        fname = os.path.basename(new_file)
        if len(fname.split(".")) != 3:
            log.error(f"File {new_file} does not appear to confirm to filename specification, ignoring")
            continue
        ftype = fname.split(".")[2]
        if ftype not in ("fasta", "csv", "bam"):
            log.error(f"File {new_file} has an invalid extension (accepted extensions are: .fasta, .csv, .bam), ignoring")
        artifact = ".".join(fname.split(".")[:2])
        fhash = hash_file(new_file)

        if unmatched_artifacts.get(artifact):
            unmatched_artifacts[artifact][ftype] = {"path": new_file, "hash": fhash}
        else:
            unmatched_artifacts[artifact] = {ftype: {"path": new_file, "hash": fhash}}
    
    to_delete = []
    # print(unmatched_artifacts)

    for artifact, triplet in unmatched_artifacts.items():
        if set(triplet.keys()) == set(["fasta", "csv", "bam"]):
            if artifact in previously_matched.keys():
                ftype_matches = {"fasta": False, "csv": False, "bam": False}
                for ftype in ("fasta", "csv", "bam"):
                    if previously_matched[artifact][ftype] == triplet[ftype]["hash"]:
                        ftype_matches[ftype] = True
                if all(ftype_matches.values()):
                    to_delete.append(artifact)
                    log.info(f"Ignoring triplet for artifact: {artifact} since identical triplet has been previously matched")
                    continue
            payload = generate_payload(artifact, triplet, uploader_code)
            file_trip_queue.put(payload)
    
    if to_delete:
        for artifact in to_delete:
            del unmatched_artifacts[artifact]
    
    new_files = set()
