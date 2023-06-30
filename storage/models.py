from sqlalchemy import Column, Text, String, ForeignKey, LargeBinary
from storage.storage import Base
from pydantic import BaseModel
from sqlalchemy.orm import relationship


# requests model
class AddUserRequest(BaseModel):
    username: str


# postgres table
class UsersTable(Base):
    __tablename__ = "users"
    user_uuid = Column(String, primary_key=True, autoincrement=False)
    token = Column(String, unique=True)
    username = Column(Text)

    audios = relationship("AudioTable", back_populates="user")


# postgres table
class AudioTable(Base):
    __tablename__ = "audio"
    audio_uuid = Column(String, primary_key=True, autoincrement=False)
    user_uuid = Column(String, ForeignKey('users.user_uuid'))
    audio_name = Column(String)
    audio_url = Column(String)
    audio = Column(LargeBinary)

    user = relationship("UsersTable", back_populates="audios")
