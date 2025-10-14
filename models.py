from pydantic import BaseModel, EmailStr, HttpUrl
from pydantic import model_validator
from static import DOMAIN


class BioLink(BaseModel):
    title: str
    url: str | str
    type: str


class PFP(BaseModel):
    pic: str
    hd: str
    default: str | None = None

    @model_validator(mode="after")
    def set_default(self):
        self.default = self.hd
        return self


class BaseUser(BaseModel):
    id: int
    username: str
    fullname: str = ""

    pfp: PFP | None = None
    url: str | str | None = None

    is_verified: bool = False
    is_private: bool = False

    @model_validator(mode="after")
    def set_url(self):
        self.url = str(DOMAIN + "/" + self.username + "/")
        return self


class TaggedUser(BaseUser):
    pass


class Owner(BaseUser):
    fb_id: int
    fullname: str
    eimu_id: int
    bio: str
    bio_links: list[BioLink | None]
    followers: int
    following: int
    posts: list["Post"] = []
    pronouns: list[str | None] = []
    bussiness_email: EmailStr | None = None
    bussiness_phone: EmailStr | None = None
    posts_count: int


class BaseMedia(BaseModel):
    url: str | str

    @model_validator(mode="after")
    def correct_url(self):
        self.url = str(self.url)
        return self


class BaseGraphMedia(BaseMedia):
    width: int | float
    height: int | float


class SideCarMedia(BaseGraphMedia):
    id: int
    shortcode: str
    type: str
    width: float
    height: float
    owner: Owner | BaseUser
    is_video: bool


class Post(BaseModel):
    id: int
    type: str
    shortcode: str
    owner: BaseUser
    title: str
    comments: int
    likes: int
    timestamp: float | int
    tagged: list[TaggedUser | None] = []
    thumbnail: str | None = None
    media: list[BaseGraphMedia | SideCarMedia] = []
    url: str | None = None
    is_video: bool = False

    @model_validator(mode="after")
    def set_url(self):
        self.url = f"{DOMAIN}/p/{self.shortcode}/"
        return self
