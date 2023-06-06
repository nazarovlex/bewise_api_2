import urllib
import uuid
import io
from fastapi import HTTPException, status
import uvicorn
from pydub import AudioSegment
from fastapi import FastAPI, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from models import UsersTable, AudioTable, AddUserRequest
from database import database, engine, Base, SessionLocal
from sqlalchemy.dialects.postgresql import insert
from config import app_ip, app_port

# FastAPI приложение
app = FastAPI()


async def create_tables():
    Base.metadata.create_all(bind=engine)


@app.on_event("startup")
async def startup():
    await database.connect()
    await create_tables()


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.post("/add_user")
async def add_user(params: AddUserRequest) -> dict:
    username = params.username
    db = SessionLocal()

    token = uuid.uuid4()
    user_uuid = uuid.uuid4()
    user_data = {
        "user_uuid": user_uuid,
        "token": token,
        "username": username,
    }
    query = insert(UsersTable).values(**user_data)
    db.execute(query)
    db.commit()
    db.close()

    return {"user_uuid": user_uuid, "token": token}


@app.post("/add_audio")
async def add_audio(file: UploadFile = File(...), user_uuid: str = Form(...), token: str = Form(...)) -> dict:
    try:
        binary_audio = await file.read()
        if not binary_audio:
            return {"Error": "Failed to upload file. Please try again."}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    audio_name = file.filename.split(".")[0]
    audio_format = file.filename.split(".")[-1]
    if audio_format != "wav":
        return {"Error": "Uploaded file must have wav format!!"}

    # Создаем временный файл в памяти
    temp_file = io.BytesIO(binary_audio)

    # Открываем аудиозапись из временного файла
    audio = AudioSegment.from_file(temp_file, format='wav')

    # Конвертируем в формат MP3
    output = io.BytesIO()
    audio.export(output, format='mp3', codec='mp3', parameters=['-q:a', '0', '-map', '0'])

    # Сбрасываем указатель файла в начало
    output.seek(0)

    db = SessionLocal()
    user = db.query(UsersTable).filter(UsersTable.user_uuid == user_uuid, UsersTable.token == token).first()
    if not user:
        return {"Error": "User with this token and UUID doesn't exist!!!"}

    audio_uuid = uuid.uuid4()
    audio_url = f"http://{app_ip}:{app_port}/record?id={audio_uuid}&user={user_uuid}"

    audio_data = {
        "audio_uuid": audio_uuid,
        "audio": output.getvalue(),
        "user_uuid": user_uuid,
        "audio_url": audio_url,
        "audio_name": audio_name
    }

    query = insert(AudioTable).values(**audio_data)
    db.execute(query)
    db.commit()
    db.close()
    return {"url": audio_url}


@app.get("/record")
async def record(audio_uuid: str = Query(description="id"), user_uuid: str = Query(description="user")) -> StreamingResponse or dict:
    db = SessionLocal()
    audio_info = db.query(AudioTable).filter(AudioTable.audio_uuid == audio_uuid, AudioTable.user_uuid == user_uuid).one()
    if not audio_info:
        return {"Error": "Audio with this id and user doesn't exist!!!"}
    binary_audio = audio_info.audio

    async def audio_generator():
        buffer = io.BytesIO(binary_audio)
        chunk = buffer.read(4096)
        while chunk:
            yield chunk
            chunk = buffer.read(4096)

    file_name = urllib.parse.quote(audio_info.audio_name, safe="")
    headers = {
        "Content-Disposition": f'attachment; filename="{file_name}.mp3"'
    }

    return StreamingResponse(audio_generator(), media_type="audio/mp3", headers=headers)


if __name__ == "__main__":
    uvicorn.run(app, host=app_ip, port=app_port)
