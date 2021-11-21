import requests
import os
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from fastapi import FastAPI, Request, status, Form, Query
from pydantic import AnyUrl, SecretStr
from typing import Optional, List
import motor.motor_asyncio
from dotenv import load_dotenv
from app.models import URLModel, User

app = FastAPI()
load_dotenv()
client = motor.motor_asyncio.AsyncIOMotorClient(os.environ["MONGODB_URL"])
uri = client.Dominuto
urls = uri.get_collection("Url")

templates = Jinja2Templates(directory="./app/templates")
app.mount("/static", StaticFiles(directory="./app/static"), name="static")


def hash_b62(b62_value: int):
    s = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    hash_str = ""
    while b62_value > 0:
        hash_str = s[b62_value % 62] + hash_str
        b62_value = int(b62_value / 62)
    return hash_str


@app.get("/")
def home(request: Request, url: Optional[str] = Query(None)):
    if not url:
        url = ""
    elif "Invalid" not in url:
        url = "Your shortened url is https://dominuto.herokuapp.com/" + url
    return templates.TemplateResponse("index.html", {"request": request, "url": url})


@app.post("/")
async def shortenUrl(
    request: Request,
    url: AnyUrl = Form(...),
    user: Optional[str] = Query(None),
    ret: Optional[str] = Query(None),
):
    url_data = await uri["Url"].find_one({"long_url": url})
    if url_data:
        if ret == "dashboard":
            data = await uri["Users"].find_one(
                {"username": user, "urls": {"$elemMatch": {"url": url}}}
            )
            if not data:
                await uri["Users"].update_one(
                    {"username": user},
                    {
                        "$push": {
                            "urls": {
                                "url": url,
                                "aliases": [url_data["short_url"]],
                            }
                        }
                    },
                )
            return RedirectResponse(
                "/dashboard?user=" + user + "&url=" + url_data["short_url"],
                status_code=status.HTTP_302_FOUND,
            )
        else:
            return RedirectResponse(
                "/?url=" + url_data["short_url"], status_code=status.HTTP_302_FOUND
            )
    try:
        _ = requests.get(url)
        counter = await uri["Counter"].find_one()
        id = counter = counter["_id"]
        await uri["Counter"].update_one({"_id": id}, {"$inc": {"value": 1}})
        counter = await uri["Counter"].find_one()
        new_data = jsonable_encoder(
            URLModel(long_url=url, short_url=hash_b62(counter["value"]).rjust(7, "0"), hits=0)
        )
        await uri["Url"].insert_one(new_data)
        if ret == "dashboard":
            data = await uri["Users"].find_one(
                {"username": user, "urls": {"$elemMatch": {"url": url}}}
            )
            if not data:
                await uri["Users"].update_one(
                    {"username": user},
                    {
                        "$push": {
                            "urls": {
                                "url": url,
                                "aliases": [hash_b62(counter["value"]).rjust(7, "0")],
                            }
                        }
                    },
                )
            return RedirectResponse(
                "/dashboard?user="
                + user
                + "&url="
                + hash_b62(counter["value"]).rjust(7, "0"),
                status_code=status.HTTP_302_FOUND,
            )
        else:
            return RedirectResponse(
                "/?url=" + hash_b62(counter["value"]).rjust(7, "0"),
                status_code=status.HTTP_302_FOUND,
            )
    except requests.ConnectionError as exception:
        if ret == "dashboard":
            return RedirectResponse(
                "/dashboard?user=" + user + "&url=Invalid Url",
                status_code=status.HTTP_302_FOUND,
            )
        else:
            return RedirectResponse(
                "/?url=Invalid Url", status_code=status.HTTP_302_FOUND
            )

@app.get("/admin_board")
async def admin(request: Request):
    hit_data = []
    async for document in uri["Url"].find({}):
        hit_data.append(document["hits"])
    return templates.TemplateResponse("dashboard-admin.html", {"request": request, "hits": hit_data})


@app.get("/dashboard")
def dashboard(
    request: Request,
    user: str = Query(...),
    url: Optional[str] = Query(None),
):
    if not url:
        url = ""
    elif "Invalid" not in url:
        url = "Your shortened url is https://dominuto.herokuapp.com/" + url
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": user, "url": url}
    )


@app.get("/custom_url")
def custom_url(
    request: Request,
    user: str = Query(...),
    url: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    if not error:
        error = ""
    if not url:
        url = ""
    else:
        url = "Your shortened url: https://dominuto.herokuapp.com/" + url
    return templates.TemplateResponse(
        "dashboard-custom.html",
        {"request": request, "user": user, "url": url, "error": error},
    )


@app.post("/custom")
async def custom(user: str = Query(...), url: str = Form(...), custom_url: str = Form(...)):
    if len(custom_url) > 10 and len(custom_url) < 7:
        return RedirectResponse(
            "/custom_url?user="
            + user
            + "&error=Custom url must be between 7 and  10 characters",
            status_code=status.HTTP_302_FOUND,
        )
    try:
        _ = requests.get(url)
        new_data = jsonable_encoder(URLModel(long_url=url, short_url=custom_url, hits=0))
        await uri["Url"].insert_one(new_data)
        data = await uri["Users"].find_one(
            {"username": user, "urls": {"$elemMatch": {"url": url}}}
        )
        if not data:
            await uri["Users"].update_one(
                {"username": user},
                {
                    "$push": {
                        "urls": {
                            "url": url,
                            "aliases": [custom_url],
                        }
                    }
                },
            )
        else:
            await uri["Users"].update_one(
                {"username": user, "urls.url": url},
                {"$push": {"urls.$.aliases": custom_url}},
            )
        return RedirectResponse(
            url="/custom_url?user=" + user + "&url=" + custom_url,
            status_code=status.HTTP_302_FOUND,
        )
    except requests.ConnectionError as exception:
        return RedirectResponse(
            "/custom_url?user=" + user + "&error=Invalid Url",
            status_code=status.HTTP_302_FOUND,
        )


@app.get("/login")
def login(request: Request, error: Optional[str] = Query(None)):
    if not error:
        error = ""
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error}
    )


@app.post("/login")
async def login_validation(username: str = Form(...), password: str = Form(...)):
    data = await uri["Users"].find_one({"username": username, "password": password})
    if data:
        if username=="admin":
            return RedirectResponse("/admin_board", status_code=status.HTTP_302_FOUND)
        return RedirectResponse(
            "/dashboard?user=" + username, status_code=status.HTTP_302_FOUND
        )
    else:
        return RedirectResponse(
            "/login?error=Invalid Username or Password",
            status_code=status.HTTP_302_FOUND,
        )


@app.get("/register")
def register(request: Request, error: Optional[str] = Query(None)):
    if not error:
        error = ""
    return templates.TemplateResponse(
        "register.html", {"request": request, "error": error}
    )


@app.post("/register")
async def register_validation(
    email: str = Form(...), username: str = Form(...), password: str = Form(...)
):
    data = await uri["Users"].find_one({"email": email})
    if data:
        return RedirectResponse(
            "/register?error=Email Already used", status_code=status.HTTP_302_FOUND
        )
    data = await uri["Users"].find_one({"username": username})
    if data:
        return RedirectResponse(
            "/register?error=Username Already used", status_code=status.HTTP_302_FOUND
        )
    if len(password) < 9:
        return RedirectResponse(
            "/register?error=Password too weak, must be 8 characters atleast",
            status_code=status.HTTP_302_FOUND,
        )
    data = jsonable_encoder(
        User(email=email, username=username, password=password, urls=[])
    )
    await uri["Users"].insert_one(data)
    return RedirectResponse(
        "/dashboard?user=" + username, status_code=status.HTTP_302_FOUND
    )


@app.get("/{url}")
async def redirectURL(url: str):
    url_data = await uri["Url"].find_one({"short_url": url})
    await uri["Url"].update_one({"short_url": url}, {'$inc': {"hits": 1}})
    return RedirectResponse(url_data["long_url"])
