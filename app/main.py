import urllib
import uuid
import io
import pydub
import uvicorn
from pydub import AudioSegment
from fastapi import FastAPI, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse, Response
from storage.models import UsersTable, AudioTable, AddUserRequest
from storage.storage import database, engine, Base, SessionLocal
from sqlalchemy.dialects.postgresql import insert
import socket
from uvicorn import Config

# FastAPI init
app = FastAPI()


# create tables in DB
async def create_tables():
    # create tables if not exist
    Base.metadata.create_all(bind=engine)


# create DB connection
@app.on_event("startup")
async def startup():
    await database.connect()
    await create_tables()


# close DB connection
@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.post("/add_user", status_code=200)
async def add_user(response: Response, params: AddUserRequest) -> dict:
    username = params.username

    # generate token and user_uuid
    token = uuid.uuid4()
    user_uuid = uuid.uuid4()

    user_data = {
        "user_uuid": user_uuid,
        "token": token,
        "username": username,
    }

    # insert new user in DB
    db = SessionLocal()
    try:
        query = insert(UsersTable).values(**user_data)
        db.execute(query)
    except Exception as error:
        db.rollback()
        response.status_code = 500
        return {"error": str(error)}

    db.commit()
    db.close()

    return {"user_uuid": user_uuid, "token": token}


@app.post("/add_audio", status_code=201)
async def add_audio(response: Response, file: UploadFile = File(...), user_uuid: str = Form(...), token: str = Form(...)) -> dict:
    db = SessionLocal()
    # checking for the existence of the user
    try:
        user = db.query(UsersTable).filter(UsersTable.user_uuid == user_uuid, UsersTable.token == token).first()
    except Exception as error:
        response.status_code = 500
        return {"error": f"get user error - {error}"}
    if not user:
        response.status_code = 400
        return {"error": "user with this token and uuid doesn't exist"}

    try:
        # read wav file
        binary_audio = await file.read()
        if not binary_audio:
            response.status_code = 400
            return {"error": "failed to upload file"}
    except Exception as error:
        response.status_code = 500
        return {"error": str(error)}

    # read file name
    audio_name = "".join(file.filename.split(".")[:-1])

    # check file format
    audio_format = file.filename.split(".")[-1]
    if audio_format != "wav":
        response.status_code = 400
        return {"error": "uploaded file must have wav format"}

    # create temporary file in memory
    temp_file = io.BytesIO(binary_audio)

    # open audio from temp_file
    try:
        audio = AudioSegment.from_file(temp_file, format='wav')
    except pydub.exceptions.CouldntDecodeError as error:
        response.status_code = 500
        return {"error": f"couldn't decode error - {error}"}

    # convert wav to mp3
    output = io.BytesIO()
    audio.export(output, format='mp3', codec='mp3', parameters=['-q:a', '0', '-map', '0'])
    output.seek(0)

    # generate audio_uuid
    audio_uuid = uuid.uuid4()

    # create url for download audio file
    ip = socket.gethostbyname(socket.gethostname())
    config = Config(app=app)
    port = config.port
    audio_url = f"http://{ip}:{port}/record?id={audio_uuid}&user={user_uuid}"

    audio_data = {
        "audio_uuid": audio_uuid,
        "audio": output.getvalue(),
        "user_uuid": user_uuid,
        "audio_url": audio_url,
        "audio_name": audio_name
    }
    # insert new audio in DB
    try:
        query = insert(AudioTable).values(**audio_data)
        db.execute(query)
    except Exception as error:
        response.status_code = 500
        return {"error": f"insert new audio error - {error}"}
    db.commit()
    db.close()

    return {"url": audio_url}


@app.get("/record", status_code=200)
async def record(response: Response, id: str = Query(description="id"),
                 user: str = Query(description="user")) -> StreamingResponse or dict:
    db = SessionLocal()
    # checking for the existence of the audio
    try:
        audio_info = db.query(AudioTable).filter(AudioTable.audio_uuid == id, AudioTable.user_uuid == user).first()
    except Exception as error:
        response.status_code = 500
        return {"error": f"find audio error - {error}"}
    if not audio_info:
        response.status_code = 400
        return {"error": "audio with this id and user doesn't exist"}
    binary_audio = audio_info.audio

    # audio generator function
    async def audio_generator():
        buffer = io.BytesIO(binary_audio)
        chunk = buffer.read(4096)
        while chunk:
            yield chunk
            chunk = buffer.read(4096)

    # process file name
    file_name = urllib.parse.quote(audio_info.audio_name, safe="")

    headers = {
        "Content-Disposition": f'attachment; filename="{file_name}.mp3"'
    }

    return StreamingResponse(audio_generator(), media_type="audio/mp3", headers=headers)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
