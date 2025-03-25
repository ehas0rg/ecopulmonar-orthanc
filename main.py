#!/usr/bin/python
# -*- coding: UTF-8 -*-

from configparser import ConfigParser
import requests
from requests.auth import HTTPBasicAuth
from datetime import date
import datetime
import time
import logging
import os
import cv2
import glob

# Obtain credentials ###################################################################################################
credentials = {}
parser = ConfigParser()
parser.read("credentials.ini")
params = parser.items("ecopulmonar")  # CHANGE select here your credentials

for param in params:
    credentials[param[0]] = param[1]

DHIS2_SERVER_URL = credentials["dhis2_server"]
DHIS2_SERVER_NAME = credentials["dhis2_server_name"]
DHIS2_USERNAME = credentials["dhis2_user"]
DHIS2_PASSWORD = credentials["dhis2_password"]
DHIS2_PAGESIZE = credentials["dhis2_page_size"]

ORTHANC_SERVER = credentials["orthanc_server"]
ORTHANC_USERNAME = credentials["orthanc_username"]
ORTHANC_PASSWORD = credentials["orthanc_password"]

PROGRAM = "d6PLRyy8l9L"  # Programa de ecografía PEDIÁTRICO
PROGRAM_STAGE = "yvhfP9fmA3W"
OU_ROOT = "uDNvnDC9DHj"
MIN_NUMBER_FRAMES = 30 # https://www.editalo.pro/videoedicion/fps/


DE_PATOLOGIA = "H2vzpa4ZFCf"

VIDEO_DE_SIN = ["g33y4QmwHz7"]

VIDEO_DE_PAT = [ "rXdrl3bPegQ", "uZAhzWxZ7Er", "SZHbLco7bNr", "DZCtmkLFDRQ","H8yuwsOTmgY" ]



# Logging setup ########################################################################################################
today = date.today()
today_str_log = today.strftime("%Y-%m-%d")
check_name = os.path.basename(__file__).replace(".py", "")
DIRECTORY_LOG = "logs"
FILENAME_LOG = DIRECTORY_LOG + "/"+ today_str_log + "-" + DHIS2_SERVER_NAME + "-" + check_name + ".log"

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
# create file handler which logs error messages
fh = logging.FileHandler(FILENAME_LOG, encoding='utf-8')
fh.setLevel(logging.DEBUG)
# create console handler which logs even debug messages
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
fh.setFormatter(formatter)
# add the handlers to logger
#logger.addHandler(ch)
logger.addHandler(fh)


########################################################################################################################


def get_resources_from_online(parent_resource, fields='*', param_filter=None, parameters=None):
    page = 0
    resources = {parent_resource: []}
    data_to_query = True
    while data_to_query:
        page += 1
        url_resource = DHIS2_SERVER_URL + parent_resource + ".json?fields=" + fields + "&pageSize=" + str(DHIS2_PAGESIZE) + "&format=json&totalPages=true&order=created:ASC&skipMeta=true&page=" + str(page)
        if param_filter:
            url_resource = url_resource + "&" + param_filter
        if parameters:
            url_resource = url_resource + "&" + parameters
        logging.debug(url_resource)
        response = requests.get(url_resource, auth=HTTPBasicAuth(DHIS2_USERNAME, DHIS2_PASSWORD))

        if response.ok:
            resources[parent_resource].extend(response.json()[parent_resource])
            if "nextPage" not in response.json()["pager"]:
                data_to_query = False
        else:
            # If response code is not ok (200), print the resulting http error code with description
            response.raise_for_status()

    return resources


def get_frames_size(instance_id):
    url = ORTHANC_SERVER+"/instances/"+instance_id
    response = requests.get(url, auth=HTTPBasicAuth(ORTHANC_USERNAME, ORTHANC_PASSWORD))
    if response.ok:
        # If there are no number of frames, returns 0
        if "NumberOfFrames" in response.json()["MainDicomTags"]:
            return int(response.json()["MainDicomTags"]["NumberOfFrames"])
        else:
            return 0
    else:
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()


def download_frames(instance_id, n_frames):
    logger.info(f"Downloading {n_frames} frames from instance {instance_id}")
    path = "images/" + instance_id
    try:
        os.mkdir(path)
    except OSError:
        logger.debug("Creation of the directory %s failed" % path)
    else:
        logger.debug("Successfully created the directory %s " % path)

    for frame_int in range(0, int(n_frames)):
        frame = str(frame_int)
        url = ORTHANC_SERVER+"/instances/"+instance_id+"/frames/"+frame+"/preview"

        response = requests.get(url, auth=HTTPBasicAuth(ORTHANC_USERNAME, ORTHANC_PASSWORD))
        if response.ok:
            filename = path+"/"+frame+".png"
            with open(filename, 'wb') as f:
                f.write(response.content)
                logger.debug(f"Saved {filename}")
        else:
            # If response code is not ok (200), print the resulting http error code with description
            response.raise_for_status()


# Returns the filename_video or None if no frames
def generate_video(instance_id):
    logger.debug("Generating video for instance " + instance_id)
    number_frames = get_frames_size(instance_id)
    if number_frames == 0:
        logger.error(f"Instance '{instance_id}' contains no frames")
        return None
    elif number_frames < MIN_NUMBER_FRAMES:
        logger.error(f"Instance '{instance_id}' contains {number_frames} frames, less than the minimun ({MIN_NUMBER_FRAMES})")
        return None
    logger.debug(f"{instance_id}. Number of frames: {number_frames}")
    download_frames(instance_id, number_frames)

    img_array = []
    size = None
    #Good order: sorted(glob.glob("../../Documents/ImageAnalysis.nosync/sliceImage/*.bmp"), key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    for filename in sorted(glob.glob('./images/' + instance_id + '/*.png'), key=lambda x: int(os.path.splitext(os.path.basename(x))[0])):
        img = cv2.imread(filename)
        height, width, layers = img.shape
        size = (width, height)
        img_array.append(img)

    logger.debug("Start video processing")
    filename_video = "videos/" + instance_id + ".mp4"
    # out = cv2.VideoWriter(filename='project.avi', fourcc=cv2.VideoWriter_fourcc(*'DIVX'), fps=30, frameSize=size)
    out = cv2.VideoWriter(filename=filename_video, fourcc=cv2.VideoWriter_fourcc(*'mp4v'), fps=30, frameSize=size)

    for i in range(len(img_array)):
        out.write(img_array[i])
    out.release()
    logger.debug("Finish video processing")
    logger.info(f"Generated video {filename_video} for instance {instance_id}")

    return filename_video


def get_event_uid(event_dict, field, value):
    for event, event_details in event_dict.items():
        for k, v in event_details.items():
            if k == field and v == value:
                return event


def get_video_de_uid(patologia,index):
    # ordered list of uids of the video DE
    if patologia == "2":
        return VIDEO_DE_SIN[index]
    elif patologia == "1":
        return VIDEO_DE_PAT[index]
    else:
        return None


def expected_max_number_video(patologia):
    if patologia == "2":
        return len(VIDEO_DE_SIN)
    elif patologia == "1":
        return len(VIDEO_DE_PAT)
    else:
        return 0 # TODO raise error or control the value


# Returns the uid of the fileresource
def post_video_dhis2(filename):
    url_resource = DHIS2_SERVER_URL + "fileResources"
    logging.debug(url_resource)
    files = {'file': open(filename, 'rb')}
    response = requests.post(url_resource, files=files, auth=HTTPBasicAuth(DHIS2_USERNAME, DHIS2_PASSWORD))
    logger.debug(response.json())
    if response.ok:
        return response.json()["response"]["fileResource"]["id"]
    else:
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()


def is_file_storaged(file_resource_uid):
    url_resource = DHIS2_SERVER_URL + "fileResources/" + file_resource_uid
    logging.debug(url_resource)
    response = requests.get(url_resource, auth=HTTPBasicAuth(DHIS2_USERNAME, DHIS2_PASSWORD))
    logger.debug(response.json())
    if response.ok:
        if response.json()["storageStatus"] == "STORED":
            return True
        else:
            return False
    else:
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()


def add_file_to_event(program_uid, event_uid, de_uid, file_resource_uid):
    url_resource = DHIS2_SERVER_URL + "events/"+event_uid+"/"+de_uid
    logging.debug(url_resource)
    data = {"program": program_uid,
            "event": event_uid,
            "dataValues": [{"dataElement": de_uid, "value": file_resource_uid}]
            }
    logging.debug(data)
    response = requests.put(url_resource, json=data, auth=HTTPBasicAuth(DHIS2_USERNAME, DHIS2_PASSWORD))
    logger.debug(response)
    if response.ok:
        logger.info(f"Updated event {event_uid}. Added DE {de_uid} with file resource {file_resource_uid}")
    else:
        # If response code is not ok (200), print the resulting http error code with description
        response.raise_for_status()


def send_video_to_dhis2(event_uid, video_path, video_de):
        logger.info(f"Event ({event_uid}): Start uploading video to dhis2 '{video_path}' in DE ({video_de})")
        file_resource_uid = post_video_dhis2(video_path)
        logger.info(f"Uploaded file {video_path} to dhis2 and generated a File Resource with uid '{file_resource_uid}'")

        flag_storage_status = False
        while not flag_storage_status:
            logger.info(f"Requesting storage status of dhis2 file resource {file_resource_uid}")
            time.sleep(5)
            flag_storage_status = is_file_storaged(file_resource_uid)
        logger.info(f"File Resource {file_resource_uid} Storage Status already STORAGED")

        # Add FileResource to the event
        add_file_to_event(PROGRAM, event_uid, video_de, file_resource_uid)


########################################################################################################################
########################################################################################################################
########################################################################################################################

# Testing data
# Retrieved for Id Único P0805211cahaPrOr the Series d8527248-83bbb5c5-8a82879a-b0eff1d5-8b12019a
# from the study 33d89009-24a9dc66-7eb18c6b-5e77ebc4-837820bb associated to the event_id DOM98UXXmxV


def main(ultrasound_date):

    ultrasound_date_dhis2 = ultrasound_date.strftime("%Y-%m-%d")

    logger.info("-------------------------------------------")
    logger.info(f"Constants: Program {PROGRAM}. Minimum of frames: {MIN_NUMBER_FRAMES}.")
    logger.info(f"Starting the process for ultrasound date {ultrasound_date_dhis2}")

    # Get all events without videos uploaded
    events_params = "program="+PROGRAM+"&programStage="+PROGRAM_STAGE+"&ou="+OU_ROOT+"&ouMode=DESCENDANTS&paging=false"
    response_events = get_resources_from_online(parent_resource="events", fields="event,trackedEntityInstance,dataValues[*]", param_filter="&filter=aY2MfS8YVdd:eq:"+ultrasound_date_dhis2, parameters=events_params)
    logger.info(f"Retrieved {len(response_events['events'])} events for ultrasound date {ultrasound_date_dhis2}")
    events_without_video = {}
    events_with_video = {}  # for debugging
    for event in response_events['events']:
        event_uid = event["event"]
        tei_uid = event["trackedEntityInstance"]
        flag = False

        # get patologia
        patologia = None
        for dv in event["dataValues"]:
            if dv["dataElement"] == DE_PATOLOGIA:
                patologia = dv["value"]
        logging.debug(f"Event={event_uid} Patologia={patologia}")

        if not patologia:
            logger.error(f"Event {event_uid} without patology")
            continue # go to the next event

        for dv in event["dataValues"]:
            if dv["dataElement"] == get_video_de_uid(patologia, index=0):  # UID of DE vídeo 1
                flag = True
        if flag:
            events_with_video[event_uid] = dict()
            events_with_video[event_uid]["tei"] = tei_uid
            events_with_video[event_uid]["patologia"] = patologia
        else:
            events_without_video[event_uid] = dict()
            events_without_video[event_uid]["tei"] = tei_uid
            events_without_video[event_uid]["patologia"] = patologia

    logger.debug(events_without_video)
    logger.info(f"{len(events_with_video)} events with video: {', '.join(events_with_video)}")
    logger.info(f"{len(events_without_video)} events without video: {', '.join(events_without_video)}")

    teis_without_video = [event["tei"] for event in events_without_video.values()]
    logger.info(f"TEIs without video {teis_without_video}")

    if not events_without_video:
        logger.info(f"There is no events without video. Skip the process.")
        logger.info("-------------------------------------------")
        return None;


    # Revisar que no hay ningun duplicado. Si hay duplicado, eliminar la TEI
    teis_duplicated = {x for x in teis_without_video if teis_without_video.count(x) > 1}

    if teis_duplicated:
        logger.error(f"There are TEIs with more than one event: {teis_duplicated}")
        teis_without_video = set(teis_without_video) - set(teis_duplicated)
        logger.info(f"Removed duplicates: {teis_duplicated}")
        logger.info(f"TEIs without video {teis_without_video}")

    # https://ecopulmonar.dhis2.ehas.org/api/trackedEntityInstances?trackedEntityInstance=gCgxGS7V57A;JaFZxFeJV0d
    teis = ";".join(teis_without_video)
    teis_params = "paging=false&trackedEntityInstance="+teis
    response_teis = get_resources_from_online(parent_resource="trackedEntityInstances", fields="trackedEntityInstance,attributes", parameters=teis_params)
    logger.info(f"Retrieved {len(response_teis['trackedEntityInstances'])} TEIs ({teis})")

    # Check that the amount requested is the same than retrieved
    if len(teis_without_video) != len(response_teis['trackedEntityInstances']):
        logger.error(f"The amount of TEIs requested ({len(teis_without_video)}) is different than the amount of TEIs retrieved ({len(response_teis['trackedEntityInstances'])})")

    # Get TEA 'id_único' (ofdWjpgwzfe) for each tei in teis_without_video
    id_unicos = set()
    for tei in response_teis['trackedEntityInstances']:
        tei_uid = tei["trackedEntityInstance"]
        for dv in tei["attributes"]:
            if dv["attribute"] == "ofdWjpgwzfe":  # UID of TEA Id único
                id_unico = dv["value"]
                id_unicos.add(id_unico)
                event_uid = get_event_uid(events_without_video, "tei", tei_uid)
                events_without_video[event_uid]["id_unico"] = id_unico
                logger.info(f"Id único '{id_unico}' for TEI '{tei_uid}' from event '{event_uid}'")

    # Check that the amount requested is the same than retrieved
    if len(id_unicos) != len(response_teis['trackedEntityInstances']):
        logger.warning(f"Not all TEIs requested contains a TEA 'Id único')")

    logger.debug(events_without_video)
    logger.info(f"List of Id Únicos retrieved: {id_unicos}")

    # Retrieve information per patient
    for id_unico in id_unicos:
        study_date = ultrasound_date
        logger.info(f"Requesting {id_unico} in orthanc server for study date {study_date.strftime('%Y%m%d')}")
        url = ORTHANC_SERVER+"/tools/find"
        # data = {
        #     "Level": "Patient",
        #     "Query": {
        #         "PatientID": id_unico
        #     }
        # }
        data = {
            "Level": "Study",
            "Expand": True,
            "Query": {
                "PatientID": id_unico,
                'StudyDate': study_date.strftime("%Y%m%d")
            }
        }
        response_study = requests.post(url, json=data, auth=HTTPBasicAuth(ORTHANC_USERNAME, ORTHANC_PASSWORD))
        logger.debug(response_study.json())
        if response_study.ok:
            if not response_study.json():  # Empty response
                logger.info(f"No Study for patient {id_unico} and date {study_date}")
            else:
                patient_id = response_study.json()[0]['ParentPatient']
                study_id = response_study.json()[0]['ID']

                if len(response_study.json()) != 1:  # More than one study in the very same date
                    logger.error(f"Retrieved more than one study for Id Único {id_unico} in {study_date.strftime('%Y%m%d')}'. Result: {response_study.json()} ")
                    continue

                if len(response_study.json()[0]['Series']) != 1:  # More than one series in the same study
                    logger.error(f"Retrieved more than one series in study {study_id} for Id Único {id_unico} in {study_date.strftime('%Y%m%d')}'. Result: {response_study.json()[0]['Series']} ")
                    continue

                series_id = response_study.json()[0]['Series'][0]
                url_series = ORTHANC_SERVER+"/series/"+series_id

                event_uid = get_event_uid(events_without_video, "id_unico", id_unico)
                events_without_video[event_uid]["orthanc_patient"] = patient_id
                events_without_video[event_uid]["orthanc_study"] = study_id
                events_without_video[event_uid]["orthanc_series"] = series_id
                logger.debug(events_without_video)

                logger.info(f"Retrieving instances for Id Único {id_unico} from series {series_id} and study {study_id} associated to event_id {event_uid}")
                response_series_details = requests.get(url_series, auth=HTTPBasicAuth(ORTHANC_USERNAME, ORTHANC_PASSWORD))
                logger.debug(response_series_details.json())

                if response_series_details.ok:
                    if response_series_details.json():  # There are instances
                        instances = response_series_details.json()["Instances"]
                        events_without_video[event_uid]["videos"] = list()

                        logger.info(f"Retrieved for Id Único {id_unico} and Series {series_id} a total number of {len(instances)} instances.")

                        # Check if it is the number of instances expected
                        if len(instances) > expected_max_number_video(events_without_video[event_uid]["patologia"]):
                            logger.error(f'Event ({event_uid}). The number of videos ({len(instances)}) are different than expected ({expected_max_number_video(events_without_video[event_uid]["patologia"])})')
                            continue

                        for idx_instances, instance in enumerate(instances):  # Keep the order
                            logger.info(f"Generating video {idx_instances+1} for instance {instance} and id único {id_unico}")
                            video_path = generate_video(instance)
                            if video_path:  # videopath could be None if an error occur
                                events_without_video[event_uid]["videos"].append(video_path)


                        logger.debug(events_without_video)
                        logger.info(f'{id_unico}: Generated {len(events_without_video[event_uid]["videos"])} videos for event ({event_uid})')

                        logger.debug(events_without_video[event_uid]["videos"])
                        if len(events_without_video[event_uid]["videos"]) > expected_max_number_video(events_without_video[event_uid]["patologia"]):
                            #logger.warning(f"Generated more videos ({len(events_without_video[event_uid]['videos'])}) than Video DE ({expected_max_number_video(events_without_video[event_uid]["patologia"])}).")
                            #logger.warning(f"Uploading only the first {expected_max_number_video(events_without_video[event_uid]["patologia"])} videos {events_without_video[event_uid]['videos'][{expected_max_number_video(events_without_video[event_uid]["patologia"])}]}.")
                            events_without_video[event_uid]["videos"] = events_without_video[event_uid]["videos"][{expected_max_number_video(events_without_video[event_uid]["patologia"])}]

                        logger.debug(events_without_video[event_uid]["videos"])
                        # Uploading videos to dhis2
                        for idx_video, video in enumerate(events_without_video[event_uid]["videos"]):
                            logger.info(f"Uploading video {idx_video+1} for event {event_uid}")
                            video_de = get_video_de_uid(events_without_video[event_uid]["patologia"], idx_video)
                            send_video_to_dhis2(event_uid, video, video_de)
                        logger.info(f'{id_unico}: Uploaded {len(events_without_video[event_uid]["videos"])} videos for event ({event_uid})')
                else:
                    # If response code is not ok (200), print the resulting http error code with description
                    response_study.raise_for_status()
        else:
            # If response code is not ok (200), print the resulting http error code with description
            response_study.raise_for_status()
    logger.info(f"Finished the process for ultrasound date {ultrasound_date_dhis2}")
    logger.info("-------------------------------------------")


if __name__ == "__main__":
    start_date = date.today()
    for x in range(0, 40):
        ultrasound_date = start_date - datetime.timedelta(days=x)
        main(ultrasound_date)

