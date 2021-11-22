from typing import Optional
import os
import requests
import json
import datetime
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from fastapi import FastAPI, Request, status, Form, Query
import motor.motor_asyncio
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from app.models import URLModel, User
import tldextract
# pylint: disable=C0116, R1705, W0621

app = FastAPI()
load_dotenv()
client = motor.motor_asyncio.AsyncIOMotorClient(os.environ["MONGODB_URL"])
uri = client.Dominuto
urls = uri.get_collection("Url")
enc = Fernet(os.environ["KEY"])

templates = Jinja2Templates(directory="./app/templates")
app.mount("/static", StaticFiles(directory="./app/static"), name="static")


def hash_b62(b62_value: int):
    hash_code = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    hash_str = ""
    while b62_value > 0:
        hash_str = hash_code[b62_value % 62] + hash_str
        b62_value = int(b62_value / 62)
    return hash_str


@app.get("/")
def home(request: Request, url: Optional[str] = Query(None)):

    text = ""
    if not url:
        url = ""
    elif "Invalid" not in url:
        url = "https://dominuto.herokuapp.com/" + url
        text = "Your shortened url is "
    return templates.TemplateResponse(
        "index.html", {"request": request, "text": text, "url": url}
    )


@app.post("/")
async def shortenUrl(
    request: Request,
    url: str = Form(...),
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
        id = counter["_id"]
        await uri["Counter"].update_one({"_id": id}, {"$inc": {"value": 1}})
        counter = await uri["Counter"].find_one()
        new_data = jsonable_encoder(
            URLModel(
                long_url=url, short_url=hash_b62(counter["value"]).rjust(7, "0"), hits=0
            )
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
            else:
                await uri["Users"].update_one(
                    {"username": user, "urls.url": url},
                    {"$push": {"urls.$.aliases": custom_url}},
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
    except (requests.ConnectionError, requests.exceptions.InvalidURL, requests.exceptions.InvalidSchema):
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
async def admin(request: Request, chart_type: str = Query(...)):
    if chart_type == "hits":
        hit_data = []
        async for document in uri["Url"].find({}):
            hit_data.append(document)
    elif chart_type == "location":
        hit_data = []
        async for document in uri["Location"].find({}):
            hit_data.append(document)
    elif chart_type == "date_hit":
        hit_data = []
        async for document in uri["DateCount"].find({}):
            hit_data.append(document)
        hit_data = sorted(hit_data, key=lambda d: d['Date'])[:7]
    elif chart_type == "domain":
        hit_data = {}
        async for document in uri["Url"].find({}):
            domain = tldextract.extract(document["long_url"])
            domain = '.'.join(domain[1:])
            if domain not in hit_data:
                hit_data[domain] = document["hits"]
            else:
                hit_data[domain] += document["hits"]
    return templates.TemplateResponse(
        "dashboard-admin.html", {"request": request, "hits": hit_data, "type": chart_type}
    )


@app.get("/dashboard")
def dashboard(
    request: Request,
    user: str = Query(...),
    url: Optional[str] = Query(None),
):

    text = ""
    if not url:
        url = ""
    elif "Invalid" not in url:
        url = "https://dominuto.herokuapp.com/" + url
        text = "Your shoterned url is "
    else:
        text = ""
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": user, "text": text, "url": url}
    )


@app.get("/manage_url")
async def manage(request: Request, user: str = Query(...)):
    data = await uri["Users"].find_one({"username": user})
    return templates.TemplateResponse(
        "dashboard-manage.html",
        {"request": request, "user": user, "data": data["urls"]},
    )


@app.post("/manage")
async def manage_post(
    user: str = Query(...), url: str = Query(...), short: str = Query(...)
):
    await uri["Users"].update_one(
        {"username": user, "urls.url": url}, {"$pullAll": {"urls.$.aliases": [short]}}
    )
    data = await uri["Users"].find_one({"username": user, "urls.url": url})
    for i in data["urls"]:
        if i["url"] == url:
            if len(i["aliases"]) < 1:
                await uri["Users"].update_one(
                    {"username": user},
                    {"$pullAll": {"urls": [{"url": url, "aliases": []}]}},
                )
    return RedirectResponse(
        "/manage_url?user=" + user, status_code=status.HTTP_302_FOUND
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
    text = ""
    if not url:
        url = ""
    else:
        url = "https://dominuto.herokuapp.com/" + url
        text = "Your shortened url: "
    return templates.TemplateResponse(
        "dashboard-custom.html",
        {"request": request, "user": user, "url": url, "text": text, "error": error},
    )


@app.post("/custom")
async def custom(
    user: str = Query(...), url: str = Form(...), custom_url: str = Form(...)
):
    if len(custom_url) > 10 or len(custom_url) < 7:
        return RedirectResponse(
            "/custom_url?user="
            + user
            + "&error=Custom url must be between 7 and  10 characters",
            status_code=status.HTTP_302_FOUND,
        )
    data = await uri["Url"].find_one({"short_url": custom_url})
    if data:
        return RedirectResponse(
            "/custom_url?user="
            + user
            + "&error=Url Already used! Kindly choose a different one",
            status_code=status.HTTP_302_FOUND,
        )
    try:
        _ = requests.get(url)
        new_data = jsonable_encoder(
            URLModel(long_url=url, short_url=custom_url, hits=0)
        )
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
    except (requests.ConnectionError, requests.exceptions.InvalidURL, requests.exceptions.InvalidSchema):
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
    data = await uri["Users"].find_one({"username": username})
    if data:
        if password == enc.decrypt(data["password"].encode()).decode("utf-8"):
            if username == "admin":
                return RedirectResponse(
                    "/admin_board?chart_type=hits", status_code=status.HTTP_302_FOUND
                )
            return RedirectResponse(
                "/dashboard?user=" + username, status_code=status.HTTP_302_FOUND
            )
        else:
            return RedirectResponse(
                "/login?error=Invalid Username or Password",
                status_code=status.HTTP_302_FOUND,
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
        User(
            email=email,
            username=username,
            password=enc.encrypt(password.encode()),
            urls=[],
        )
    )
    await uri["Users"].insert_one(data)
    return RedirectResponse(
        "/dashboard?user=" + username, status_code=status.HTTP_302_FOUND
    )


@app.get("/{url}")
async def redirect_url(url: str):
    url_data = await uri["Url"].find_one({"short_url": url})
    if url_data:
        url_l = f"https://ipinfo.io/json"       # getting records from getting ip address
        headers = {
            'accept': "application/json",
            'content-type': "application/json"
            }
        response = requests.request("GET", url_l, headers=headers)
        city = json.loads(response.text)["city"]
        data = await uri["Location"].find_one({"city": city})
        if data:
            await uri["Location"].update_one({"city": city}, {'$inc': {"hits": 1}})
        else:
            await uri["Location"].insert_one({"city": city, "hits": 1})
        await uri["Url"].update_one({"short_url": url}, {"$inc": {"hits": 1}})
        current_date = datetime.datetime.now()
        data  = await uri["DateCount"].find_one({"Date": str(current_date.day)+"/"+str(current_date.month)+"/"+str(current_date.year)})
        if data:
            await uri["DateCount"].update_one({"Date": str(current_date.day)+"/"+str(current_date.month)+"/"+str(current_date.year)}, {"$inc": {"Hits": 1}})
        else:
            await uri["DateCount"].insert_one({"Date": str(current_date.day)+"/"+str(current_date.month)+"/"+str(current_date.year), "Hits": 1})
        return RedirectResponse(url_data["long_url"])
