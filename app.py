"""
YT Analytics Pro
No AI needed — channel advisor runs 100% offline from your stats.

Run:
  pip install flask requests
  python yt.py

Set your keys at the top of this file (or via env vars):
  YOUTUBE_API_KEY=...
  CHANNEL_ID=...

Open: http://127.0.0.1:5000
"""

import os
import re
from datetime import datetime
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

# ═══════════════════════════════════════════════
#  CONFIG — paste your keys here
# ═══════════════════════════════════════════════
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "YOUR_YOUTUBE_API_KEY")
CHANNEL_ID      = os.getenv("CHANNEL_ID",      "YOUR_CHANNEL_ID")
# ═══════════════════════════════════════════════

YT = "https://www.googleapis.com/youtube/v3"


def parse_duration(s: str) -> int:
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', s or "")
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def fmt_duration(sec: int) -> str:
    if sec >= 3600:
        return f"{sec//3600}:{(sec%3600)//60:02d}:{sec%60:02d}"
    return f"{sec//60}:{sec%60:02d}"


def best_thumb(thumbnails: dict) -> str:
    for q in ("maxres", "standard", "high", "medium", "default"):
        if q in thumbnails:
            return thumbnails[q]["url"]
    return ""


def check_live_status() -> bool:
    try:
        res = requests.get(
            f"{YT}/search",
            params=dict(part="snippet", channelId=CHANNEL_ID,
                        eventType="live", type="video", key=YOUTUBE_API_KEY),
            timeout=8
        ).json()
        return len(res.get("items", [])) > 0
    except Exception:
        return False


def get_youtube_stats() -> dict:
    if YOUTUBE_API_KEY == "YOUR_YOUTUBE_API_KEY":
        return {"error": "Set your YOUTUBE_API_KEY at the top of yt.py"}
    if CHANNEL_ID == "YOUR_CHANNEL_ID":
        return {"error": "Set your CHANNEL_ID at the top of yt.py"}
    try:
        ch = requests.get(
            f"{YT}/channels",
            params=dict(part="snippet,statistics,brandingSettings,contentDetails",
                        id=CHANNEL_ID, key=YOUTUBE_API_KEY),
            timeout=10
        ).json()

        if not ch.get("items"):
            return {"error": "Channel not found. Check your CHANNEL_ID."}

        item    = ch["items"][0]
        sn      = item["snippet"]
        st      = item["statistics"]
        uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]

        info = {
            "title":        sn["title"],
            "thumbnail":    best_thumb(sn.get("thumbnails", {})),
            "banner":       item.get("brandingSettings", {}).get("image", {}).get("bannerExternalUrl", ""),
            "description":  sn.get("description", ""),
            "country":      sn.get("country", ""),
            "created":      sn.get("publishedAt", "")[:10],
            "subs":         int(st.get("subscriberCount", 0)),
            "total_views":  int(st.get("viewCount", 0)),
            "total_videos": int(st.get("videoCount", 0)),
            "fetched_at":   datetime.utcnow().strftime("%H:%M UTC"),
            "is_live":      check_live_status(),
        }

        all_ids, next_page = [], None
        while len(all_ids) < 50:
            params = dict(part="contentDetails", maxResults=50,
                          playlistId=uploads, key=YOUTUBE_API_KEY)
            if next_page:
                params["pageToken"] = next_page
            pl = requests.get(f"{YT}/playlistItems", params=params, timeout=10).json()
            batch = [v["contentDetails"]["videoId"] for v in pl.get("items", [])]
            all_ids.extend(batch)
            next_page = pl.get("nextPageToken")
            if not next_page:
                break

        ids = all_ids[:50]
        if ids:
            vd = requests.get(
                f"{YT}/videos",
                params=dict(part="snippet,statistics,contentDetails",
                            id=",".join(ids), key=YOUTUBE_API_KEY),
                timeout=10
            ).json()

            videos, shorts = [], []
            total_likes = total_comments = total_views_recent = 0

            for v in vd.get("items", []):
                vsn = v["snippet"]
                vst = v["statistics"]
                dur = parse_duration(v["contentDetails"]["duration"])
                lk  = int(vst.get("likeCount",    0))
                cm  = int(vst.get("commentCount", 0))
                vw  = int(vst.get("viewCount",    0))
                total_likes        += lk
                total_comments     += cm
                total_views_recent += vw
                rec = {
                    "id":         v["id"],
                    "title":      vsn["title"],
                    "thumb":      best_thumb(vsn.get("thumbnails", {})),
                    "published":  vsn.get("publishedAt", "")[:10],
                    "views":      vw,
                    "likes":      lk,
                    "comments":   cm,
                    "dur_sec":    dur,
                    "dur_fmt":    fmt_duration(dur),
                    "is_short":   dur > 0 and dur <= 60,
                    "engagement": round((lk + cm) / vw * 100, 2) if vw else 0,
                }
                videos.append(rec)
                if rec["is_short"]:
                    shorts.append(rec)

            videos_by_date  = sorted(videos, key=lambda x: x["published"], reverse=True)
            videos_by_views = sorted(videos, key=lambda x: x["views"],     reverse=True)

            info.update({
                "videos":          videos_by_date,
                "videos_by_views": videos_by_views,
                "shorts":          shorts,
                "total_likes":     total_likes,
                "total_comments":  total_comments,
                "avg_views":       total_views_recent // len(videos) if videos else 0,
                "top_video":       videos_by_views[0] if videos_by_views else None,
            })

        return info
    except Exception as exc:
        return {"error": str(exc)}


@app.route("/api/stats")
def api_stats():
    return jsonify(get_youtube_stats())


@app.route("/")
def index():
    return PAGE


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>YT Analytics Pro</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Space+Grotesk:wght@300;400;500;600;700&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
:root {
  --bg:#07070a;--bg2:#0d0d12;--bg3:#131318;--bg4:#1a1a22;
  --red:#ff2d55;--red2:#cc1f3f;--orange:#ff6a00;
  --green:#00e5a0;--gold:#ffc940;--blue:#3d9bff;
  --text:#eeeef5;--muted:#52526a;--muted2:#8585a8;
  --border:rgba(255,255,255,.06);--border2:rgba(255,255,255,.11);
  --mono:'DM Mono',monospace;--body:'Space Grotesk',sans-serif;--display:'Bebas Neue',sans-serif;
  --r:10px;--r2:16px;--r3:22px;
}
*,::before,::after{box-sizing:border-box;margin:0;padding:0;}
html{scroll-behavior:smooth;}
body{font-family:var(--body);background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden;}
body::after{content:'';position:fixed;inset:0;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E");opacity:.025;pointer-events:none;z-index:9999;}

#topbar{position:fixed;top:0;width:100%;z-index:200;background:rgba(7,7,10,.9);backdrop-filter:blur(28px) saturate(1.5);border-bottom:1px solid var(--border);height:60px;display:flex;align-items:center;padding:0 2rem;gap:1.2rem;}
.tb-logo{font-family:var(--display);font-size:1.5rem;letter-spacing:.05em;color:var(--text);display:flex;align-items:center;gap:.55rem;flex-shrink:0;line-height:1;}
.logo-icon{width:28px;height:28px;background:var(--red);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:.7rem;color:#fff;box-shadow:0 0 14px rgba(255,45,85,.5);}
.tb-nav{display:flex;gap:2px;margin-left:auto;}
.tb-btn{font-family:var(--mono);font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;background:none;border:none;color:var(--muted);cursor:pointer;padding:.42rem 1rem;border-radius:8px;transition:color .15s,background .15s;}
.tb-btn:hover{color:var(--text);background:rgba(255,255,255,.05);}
.tb-btn.on{color:var(--red);background:rgba(255,45,85,.08);}
.live-pill{font-family:var(--mono);font-size:.56rem;letter-spacing:.12em;text-transform:uppercase;color:#fff;background:var(--red);padding:.22rem .6rem;border-radius:20px;display:flex;align-items:center;gap:.32rem;box-shadow:0 0 18px rgba(255,45,85,.5);}
.live-dot{width:5px;height:5px;border-radius:50%;background:#fff;animation:pulse 1.4s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.3;transform:scale(.7)}}
.refresh-btn{font-family:var(--mono);font-size:.58rem;letter-spacing:.07em;background:rgba(255,255,255,.04);border:1px solid var(--border2);color:var(--muted2);cursor:pointer;padding:.32rem .75rem;border-radius:8px;display:flex;align-items:center;gap:.38rem;transition:all .15s;}
.refresh-btn:hover{color:var(--text);border-color:rgba(255,255,255,.22);}
.refresh-btn.spinning i{animation:spin .7s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}

main{max-width:1380px;margin:0 auto;padding:76px 2rem 6rem;}
.tab{display:none;}
.tab.show{display:block;animation:fadeIn .3s ease;}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

.hero{display:grid;grid-template-columns:auto 1fr auto;gap:1.6rem;align-items:center;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r3);padding:1.75rem 2.2rem;margin-bottom:1.2rem;position:relative;overflow:hidden;}
.hero-bg{position:absolute;inset:0;background:radial-gradient(ellipse 40% 80% at 0% 50%,rgba(255,45,85,.07) 0%,transparent 60%);pointer-events:none;}
.hero-avatar{width:74px;height:74px;border-radius:50%;object-fit:cover;border:2.5px solid var(--red);box-shadow:0 0 0 5px rgba(255,45,85,.12),0 0 32px rgba(255,45,85,.22);position:relative;z-index:1;}
.hero-name{font-family:var(--display);font-size:clamp(1.8rem,4vw,3rem);letter-spacing:.02em;line-height:1;margin-bottom:.25rem;}
.hero-sub{font-family:var(--mono);font-size:.62rem;color:var(--muted2);letter-spacing:.05em;}
.hero-right{text-align:right;}
.hero-time{font-family:var(--mono);font-size:.58rem;color:var(--muted);}

.kpi-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--border);border:1px solid var(--border);border-radius:var(--r2);overflow:hidden;margin-bottom:1.2rem;}
@media(max-width:900px){.kpi-grid{grid-template-columns:repeat(3,1fr);}}
@media(max-width:500px){.kpi-grid{grid-template-columns:repeat(2,1fr);}}
.kpi{background:var(--bg2);padding:1.25rem 1.5rem;transition:background .15s;position:relative;}
.kpi::after{content:'';position:absolute;bottom:0;left:0;right:0;height:2px;background:transparent;transition:background .2s;}
.kpi:hover{background:var(--bg3);}
.kpi:hover::after{background:linear-gradient(90deg,var(--red),var(--orange));}
.kpi-icon{font-size:.72rem;color:var(--red);margin-bottom:.65rem;}
.kpi-label{font-family:var(--mono);font-size:.55rem;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);margin-bottom:.45rem;}
.kpi-value{font-family:var(--display);font-size:2rem;letter-spacing:.02em;line-height:1;}
.kpi-sub{font-family:var(--mono);font-size:.52rem;color:var(--muted);margin-top:.28rem;}

.sec-head{display:flex;align-items:center;gap:1rem;margin-bottom:1rem;}
.sec-title{font-family:var(--display);font-size:1.35rem;letter-spacing:.03em;white-space:nowrap;}
.sec-rule{flex:1;height:1px;background:var(--border2);}
.sec-count{font-family:var(--mono);font-size:.56rem;color:var(--muted);letter-spacing:.1em;background:var(--bg3);border:1px solid var(--border2);padding:.18rem .55rem;border-radius:20px;white-space:nowrap;}

.chart-card{background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r2);padding:1.5rem;margin-bottom:1.2rem;}
.chart-title{font-family:var(--mono);font-size:.6rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:1.1rem;}
#bar-chart{display:flex;align-items:flex-end;gap:4px;height:90px;}
.bar-wrap{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;cursor:pointer;}
.bar{width:100%;border-radius:4px 4px 0 0;background:linear-gradient(180deg,var(--red),rgba(255,45,85,.4));transition:filter .15s;min-height:2px;}
.bar-wrap:hover .bar{filter:brightness(1.3);}
.bar-lbl{font-family:var(--mono);font-size:.42rem;color:var(--muted);text-align:center;writing-mode:vertical-rl;transform:rotate(180deg);height:40px;}

.vgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:.9rem;}
.vgrid-wide{grid-template-columns:repeat(auto-fill,minmax(232px,1fr));}
.vcard{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r2);overflow:hidden;cursor:pointer;transition:border-color .18s,transform .18s,box-shadow .18s;}
.vcard:hover{border-color:rgba(255,45,85,.38);transform:translateY(-3px);box-shadow:0 14px 40px rgba(0,0,0,.65);}
.vthumb{position:relative;aspect-ratio:16/9;overflow:hidden;background:var(--bg3);}
.vthumb img{width:100%;height:100%;object-fit:cover;transition:transform .38s ease;display:block;}
.vcard:hover .vthumb img{transform:scale(1.06);}
.vplay{position:absolute;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;opacity:0;transition:opacity .2s;}
.vcard:hover .vplay{opacity:1;}
.vplay-icon{width:44px;height:44px;border-radius:50%;background:rgba(255,45,85,.92);display:flex;align-items:center;justify-content:center;font-size:.9rem;color:#fff;transform:scale(.82);transition:transform .2s;}
.vcard:hover .vplay-icon{transform:scale(1);}
.vdur{position:absolute;bottom:.4rem;right:.4rem;background:rgba(0,0,0,.88);font-family:var(--mono);font-size:.56rem;padding:.08rem .38rem;border-radius:4px;color:#fff;}
.vshort-badge{position:absolute;top:.4rem;left:.4rem;background:var(--red);font-family:var(--mono);font-size:.5rem;letter-spacing:.1em;padding:.1rem .42rem;border-radius:4px;color:#fff;}
.vmeta{padding:.8rem .95rem .95rem;}
.vtitle{font-size:.82rem;font-weight:500;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-bottom:.5rem;}
.vpub{font-family:var(--mono);font-size:.55rem;color:var(--muted);margin-bottom:.4rem;}
.vstats{display:flex;gap:.7rem;font-family:var(--mono);font-size:.58rem;color:var(--muted2);}
.vstats span{display:flex;align-items:center;gap:.22rem;}
.vstats i{color:rgba(255,45,85,.65);font-size:.58rem;}

.top-vid-card{background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r2);overflow:hidden;cursor:pointer;display:grid;grid-template-columns:240px 1fr;margin-bottom:1.2rem;transition:box-shadow .2s;position:relative;}
.top-vid-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--red),var(--orange),var(--gold));}
.top-vid-card:hover{box-shadow:0 16px 48px rgba(0,0,0,.7);}
.top-vid-thumb{position:relative;overflow:hidden;}
.top-vid-thumb img{width:100%;height:100%;object-fit:cover;transition:transform .4s;}
.top-vid-card:hover .top-vid-thumb img{transform:scale(1.04);}
.top-vid-badge{position:absolute;top:.6rem;left:.6rem;font-family:var(--display);font-size:.8rem;letter-spacing:.06em;background:var(--gold);color:#000;padding:.1rem .55rem;border-radius:4px;}
.top-vid-meta{padding:1.4rem 1.6rem;display:flex;flex-direction:column;justify-content:center;gap:.6rem;}
.top-vid-title{font-size:1rem;font-weight:600;line-height:1.5;}
.top-vid-stats{display:flex;gap:1.4rem;flex-wrap:wrap;}
.top-vid-stat{display:flex;flex-direction:column;gap:.18rem;}
.top-vid-stat-val{font-family:var(--display);font-size:1.4rem;letter-spacing:.02em;}
.top-vid-stat-lbl{font-family:var(--mono);font-size:.55rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;}

.two-col{display:grid;grid-template-columns:1fr 1fr;gap:1.8rem;margin-top:1.5rem;}
@media(max-width:860px){.two-col{grid-template-columns:1fr;}}

.filter-bar{display:flex;gap:.45rem;margin-bottom:1.25rem;flex-wrap:wrap;}
.filter-btn{font-family:var(--mono);font-size:.58rem;letter-spacing:.08em;text-transform:uppercase;background:var(--bg3);border:1px solid var(--border2);color:var(--muted2);cursor:pointer;padding:.33rem .85rem;border-radius:20px;transition:all .15s;}
.filter-btn:hover{color:var(--text);}
.filter-btn.on{background:rgba(255,45,85,.1);border-color:rgba(255,45,85,.38);color:var(--red);}

.search-wrap{position:relative;margin-bottom:1.25rem;}
.search-inp{width:100%;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r);padding:.62rem 1rem .62rem 2.4rem;color:var(--text);font-family:var(--body);font-size:.84rem;outline:none;transition:border-color .15s;}
.search-inp:focus{border-color:rgba(255,45,85,.38);}
.search-inp::placeholder{color:var(--muted);}
.search-icon{position:absolute;left:.82rem;top:50%;transform:translateY(-50%);color:var(--muted);font-size:.78rem;pointer-events:none;}

.about-banner{width:100%;height:220px;object-fit:cover;border-radius:var(--r2);margin-bottom:1.5rem;border:1px solid var(--border);}
.about-grid{display:grid;grid-template-columns:1fr 260px;gap:1.5rem;}
@media(max-width:700px){.about-grid{grid-template-columns:1fr;}}
.about-box{background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r2);padding:1.75rem;}
.about-box h3{font-family:var(--mono);font-size:.62rem;font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:1rem;}
.about-desc{font-size:.87rem;line-height:1.9;color:rgba(238,238,245,.6);white-space:pre-line;}
.about-stats{display:flex;flex-direction:column;gap:.7rem;}
.about-stat{background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r);padding:1.1rem 1.3rem;}
.about-stat-label{font-family:var(--mono);font-size:.55rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:.32rem;}
.about-stat-value{font-family:var(--display);font-size:1.65rem;letter-spacing:.02em;}

.overlay{display:none;position:fixed;inset:0;z-index:500;background:rgba(0,0,0,.94);backdrop-filter:blur(14px);align-items:center;justify-content:center;}
.overlay.open{display:flex;animation:fIn .18s ease;}
@keyframes fIn{from{opacity:0}to{opacity:1}}
.modal-box{width:96%;max-width:920px;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r3);overflow:hidden;animation:mPop .22s ease;}
@keyframes mPop{from{opacity:0;transform:scale(.92)}to{opacity:1;transform:scale(1)}}
.modal-head{display:flex;align-items:center;gap:1rem;padding:.9rem 1.3rem;border-bottom:1px solid var(--border);}
.modal-title{font-size:.84rem;font-weight:500;flex:1;line-height:1.3;}
.modal-close{background:rgba(255,255,255,.07);border:none;color:var(--text);width:28px;height:28px;border-radius:50%;cursor:pointer;font-size:.78rem;transition:background .15s;display:flex;align-items:center;justify-content:center;}
.modal-close:hover{background:rgba(255,255,255,.14);}
.modal-frame{aspect-ratio:16/9;background:#000;}
.modal-frame iframe{width:100%;height:100%;border:none;display:block;}

/* ── ADVISOR FAB ── */
.adv-fab{position:fixed;bottom:1.75rem;right:1.75rem;width:54px;height:54px;border-radius:15px;background:linear-gradient(135deg,var(--red),var(--orange));border:none;color:#fff;font-size:1.2rem;cursor:pointer;z-index:300;box-shadow:0 6px 26px rgba(255,45,85,.42);transition:transform .18s,box-shadow .18s;display:flex;align-items:center;justify-content:center;}
.adv-fab:hover{transform:scale(1.08);box-shadow:0 10px 34px rgba(255,45,85,.55);}
.adv-fab-label{position:fixed;bottom:5rem;right:1.75rem;font-family:var(--mono);font-size:.56rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);z-index:300;text-align:center;width:54px;}

/* ── ADVISOR PANEL ── */
.adv-panel{position:fixed;bottom:5.5rem;right:1.75rem;width:380px;max-height:640px;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r3);display:flex;flex-direction:column;z-index:299;overflow:hidden;transform:translateY(16px) scale(.96);opacity:0;pointer-events:none;transition:transform .22s ease,opacity .22s ease;box-shadow:0 28px 90px rgba(0,0,0,.85);}
.adv-panel.open{transform:none;opacity:1;pointer-events:all;}

.adv-head{padding:.9rem 1.1rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:.7rem;flex-shrink:0;background:linear-gradient(135deg,rgba(255,45,85,.07),rgba(255,106,0,.04));}
.adv-avatar{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--red),var(--orange));display:flex;align-items:center;justify-content:center;font-size:.82rem;flex-shrink:0;}
.adv-head-title{font-size:.88rem;font-weight:600;line-height:1;}
.adv-head-sub{font-family:var(--mono);font-size:.53rem;color:var(--green);margin-top:.1rem;letter-spacing:.04em;}
.adv-x{margin-left:auto;background:none;border:none;color:var(--muted);cursor:pointer;font-size:.82rem;transition:color .15s;display:flex;align-items:center;justify-content:center;}
.adv-x:hover{color:var(--text);}

.adv-body{flex:1;overflow-y:auto;padding:.9rem;}
.adv-body::-webkit-scrollbar{width:2px;}
.adv-body::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px;}

/* home topic list */
.adv-intro{font-family:var(--mono);font-size:.61rem;color:var(--muted2);letter-spacing:.03em;margin-bottom:.75rem;line-height:1.65;padding:.65rem .8rem;background:var(--bg3);border-radius:10px;border:1px solid var(--border);}
.adv-home{display:flex;flex-direction:column;gap:.45rem;}
.topic-btn{background:var(--bg3);border:1px solid var(--border2);border-radius:12px;padding:.72rem 1rem;cursor:pointer;text-align:left;color:var(--text);transition:border-color .15s,background .15s;display:flex;align-items:center;gap:.75rem;width:100%;}
.topic-btn:hover{border-color:rgba(255,45,85,.4);background:rgba(255,45,85,.05);}
.topic-btn:active{transform:scale(.98);}
.topic-icon{font-size:1.05rem;width:26px;text-align:center;flex-shrink:0;}
.t-title{font-size:.81rem;font-weight:600;display:block;margin-bottom:.08rem;}
.t-sub{font-family:var(--mono);font-size:.54rem;color:var(--muted);letter-spacing:.03em;}
.topic-arr{color:var(--muted);font-size:.58rem;margin-left:auto;flex-shrink:0;}

/* answer view */
.adv-answer{display:flex;flex-direction:column;gap:.7rem;}
.back-btn{background:none;border:1px solid var(--border2);border-radius:8px;padding:.3rem .7rem;color:var(--muted2);cursor:pointer;font-family:var(--mono);font-size:.57rem;letter-spacing:.06em;display:inline-flex;align-items:center;gap:.35rem;transition:color .15s,border-color .15s;align-self:flex-start;}
.back-btn:hover{color:var(--text);border-color:rgba(255,255,255,.2);}
.answer-title{font-family:var(--display);font-size:1.1rem;letter-spacing:.03em;line-height:1.2;}
.answer-body{font-size:.81rem;line-height:1.8;color:rgba(238,238,245,.82);}
.answer-body strong{color:var(--text);font-weight:600;}
.clr-good{color:var(--green);font-weight:600;}
.clr-warn{color:var(--gold);font-weight:600;}
.clr-red{color:var(--red);font-weight:600;}

.stat-row{display:flex;gap:.5rem;margin:.5rem 0;flex-wrap:wrap;}
.stat-box{background:var(--bg3);border:1px solid var(--border2);border-radius:10px;padding:.6rem .85rem;flex:1;min-width:72px;}
.stat-box-val{font-family:var(--display);font-size:1.15rem;letter-spacing:.02em;}
.stat-box-lbl{font-family:var(--mono);font-size:.48rem;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;margin-top:.12rem;}

.ans-list{margin:.4rem 0 .4rem 1.1rem;}
.ans-list li{margin-bottom:.32rem;font-size:.8rem;line-height:1.6;}
.tip-box{background:rgba(255,45,85,.07);border:1px solid rgba(255,45,85,.2);border-left:3px solid var(--red);border-radius:0 10px 10px 0;padding:.75rem 1rem;font-size:.79rem;line-height:1.7;margin-top:.4rem;}
.tip-lbl{font-family:var(--mono);font-size:.53rem;letter-spacing:.1em;text-transform:uppercase;color:var(--red);margin-bottom:.3rem;font-weight:500;}

.spinner-wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:6rem;gap:1rem;}
.spinner{width:34px;height:34px;border-radius:50%;border:2.5px solid var(--border2);border-top-color:var(--red);animation:spin .7s linear infinite;}
.spinner-txt{font-family:var(--mono);font-size:.6rem;color:var(--muted);letter-spacing:.1em;}
.empty{text-align:center;padding:3rem;font-family:var(--mono);font-size:.68rem;color:var(--muted);}
.error-banner{background:rgba(255,45,85,.08);border:1px solid rgba(255,45,85,.25);border-radius:var(--r2);padding:1.2rem 1.5rem;font-family:var(--mono);font-size:.72rem;color:rgba(255,45,85,.9);line-height:1.6;margin-bottom:1.2rem;}

@media(max-width:640px){
  .hero{grid-template-columns:auto 1fr;gap:1rem;}
  .hero-right{display:none;}
  main{padding:70px 1rem 6rem;}
  .adv-panel{width:calc(100vw - 2rem);right:1rem;}
  .top-vid-card{grid-template-columns:1fr;}
}
</style>
</head>
<body>

<div id="topbar">
  <div class="tb-logo">
    <div class="logo-icon"><i class="fa fa-play"></i></div>
    YT Analytics
  </div>
  <nav class="tb-nav">
    <button class="tb-btn on" onclick="switchTab('home',this)">Overview</button>
    <button class="tb-btn"   onclick="switchTab('videos',this)">Videos</button>
    <button class="tb-btn"   onclick="switchTab('about',this)">About</button>
  </nav>
  <div id="live-indicator" style="display:none">
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
  </div>
  <button class="refresh-btn" id="refresh-btn" onclick="reload()">
    <i class="fa fa-rotate-right"></i> Refresh
  </button>
</div>

<main>
  <div id="tab-home" class="tab show">
    <div class="spinner-wrap" id="loader">
      <div class="spinner"></div>
      <div class="spinner-txt">Fetching channel data…</div>
    </div>
    <div id="home-data" style="display:none">
      <div id="error-area"></div>
      <div class="hero">
        <div class="hero-bg"></div>
        <img id="ch-avatar" class="hero-avatar" src="" alt="">
        <div>
          <div class="hero-name" id="ch-name"></div>
          <div class="hero-sub" id="ch-meta"></div>
        </div>
        <div class="hero-right">
          <div class="hero-time" id="ch-time"></div>
        </div>
      </div>
      <div class="kpi-grid" id="kpi-strip"></div>
      <div id="top-vid-wrap"></div>
      <div class="chart-card" id="chart-card" style="display:none">
        <div class="chart-title">Recent uploads — views</div>
        <div id="bar-chart"></div>
      </div>
      <div class="two-col">
        <div>
          <div class="sec-head">
            <div class="sec-title">Recent Uploads</div>
            <div class="sec-rule"></div>
            <div class="sec-count" id="recent-tag"></div>
          </div>
          <div class="vgrid" id="grid-recent"></div>
        </div>
        <div>
          <div class="sec-head">
            <div class="sec-title">Shorts</div>
            <div class="sec-rule"></div>
            <div class="sec-count" id="shorts-tag"></div>
          </div>
          <div class="vgrid" id="grid-shorts"></div>
        </div>
      </div>
    </div>
  </div>

  <div id="tab-videos" class="tab">
    <div class="sec-head" style="margin-bottom:1rem">
      <div class="sec-title">All Videos</div>
      <div class="sec-rule"></div>
      <div class="sec-count" id="all-tag"></div>
    </div>
    <div class="search-wrap">
      <i class="fa fa-search search-icon"></i>
      <input class="search-inp" id="search-inp" placeholder="Search videos…" oninput="filterVideos()">
    </div>
    <div class="filter-bar">
      <button class="filter-btn on" onclick="setSort('date',this)">Newest</button>
      <button class="filter-btn" onclick="setSort('views',this)">Most Views</button>
      <button class="filter-btn" onclick="setSort('likes',this)">Most Likes</button>
      <button class="filter-btn" onclick="setSort('engagement',this)">Top Engagement</button>
    </div>
    <div class="vgrid vgrid-wide" id="grid-all"></div>
  </div>

  <div id="tab-about" class="tab">
    <img id="about-banner" class="about-banner" src="" alt="" onerror="this.style.display='none'">
    <div class="about-grid">
      <div class="about-box">
        <h3>About the Channel</h3>
        <p class="about-desc" id="about-desc"></p>
      </div>
      <div class="about-stats" id="about-stats"></div>
    </div>
  </div>
</main>

<div class="overlay" id="vid-overlay">
  <div class="modal-box">
    <div class="modal-head">
      <div class="modal-title" id="modal-title"></div>
      <button class="modal-close" onclick="closeVid()"><i class="fa fa-times"></i></button>
    </div>
    <div class="modal-frame">
      <iframe id="vid-frame" allowfullscreen allow="autoplay;encrypted-media"></iframe>
    </div>
  </div>
</div>

<!-- ADVISOR FAB -->
<div class="adv-fab-label">Advisor</div>
<button class="adv-fab" onclick="toggleAdvisor()" title="Channel Advisor">
  <i class="fa-solid fa-chart-line"></i>
</button>

<!-- ADVISOR PANEL -->
<div class="adv-panel" id="adv-panel">
  <div class="adv-head">
    <div class="adv-avatar"><i class="fa-solid fa-chart-line"></i></div>
    <div>
      <div class="adv-head-title">Channel Advisor</div>
      <div class="adv-head-sub">100% offline · your real stats</div>
    </div>
    <button class="adv-x" onclick="toggleAdvisor()"><i class="fa fa-times"></i></button>
  </div>
  <div class="adv-body" id="adv-body"></div>
</div>

<script>
const $ = id => document.getElementById(id);

function fmt(n) {
  if (n >= 1e9) return (n/1e9).toFixed(1)+'B';
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return String(n || 0);
}
function safe(s) { return String(s).replace(/'/g,"\\'").replace(/"/g,'&quot;'); }

let allVideos = [], currentSort = 'date', channelData = null;

function vcard(v) {
  const badge = v.is_short ? '<span class="vshort-badge">SHORT</span>' : '';
  return `<div class="vcard" onclick="openVid('${safe(v.id)}','${safe(v.title)}')">
    <div class="vthumb"><img src="${v.thumb}" alt="" loading="lazy">
      <div class="vplay"><div class="vplay-icon"><i class="fa fa-play"></i></div></div>
      ${badge}<span class="vdur">${v.dur_fmt||'?'}</span></div>
    <div class="vmeta">
      <div class="vtitle">${v.title}</div>
      <div class="vpub">${v.published}</div>
      <div class="vstats">
        <span><i class="fa fa-eye"></i>${fmt(v.views)}</span>
        <span><i class="fa fa-thumbs-up"></i>${fmt(v.likes)}</span>
        <span><i class="fa fa-comment"></i>${fmt(v.comments)}</span>
      </div>
    </div></div>`;
}

function setSort(key, btn) {
  currentSort = key;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  filterVideos();
}

function filterVideos() {
  const q = $('search-inp').value.toLowerCase();
  let list = allVideos.filter(v => v.title.toLowerCase().includes(q));
  if (currentSort==='views')           list.sort((a,b)=>b.views-a.views);
  else if (currentSort==='likes')      list.sort((a,b)=>b.likes-a.likes);
  else if (currentSort==='engagement') list.sort((a,b)=>b.engagement-a.engagement);
  else list.sort((a,b)=>b.published.localeCompare(a.published));
  $('grid-all').innerHTML = list.length ? list.map(vcard).join('') : '<div class="empty">No videos match</div>';
  $('all-tag').textContent = list.length+' videos';
}

function renderChart(videos) {
  const top = [...videos].sort((a,b)=>b.published.localeCompare(a.published)).slice(0,20);
  if (!top.length) return;
  const maxV = Math.max(...top.map(v=>v.views), 1);
  $('bar-chart').innerHTML = top.map(v=>`
    <div class="bar-wrap" onclick="openVid('${safe(v.id)}','${safe(v.title)}')" title="${v.title} · ${fmt(v.views)} views">
      <div class="bar" style="height:${Math.max(4,Math.round(v.views/maxV*82))}px"></div>
      <div class="bar-lbl">${v.published.slice(5)}</div>
    </div>`).join('');
  $('chart-card').style.display='block';
}

function renderTopVid(v) {
  if (!v) return;
  $('top-vid-wrap').innerHTML=`
    <div class="top-vid-card" onclick="openVid('${safe(v.id)}','${safe(v.title)}')">
      <div class="top-vid-thumb"><img src="${v.thumb}" alt=""><span class="top-vid-badge">TOP VIDEO</span></div>
      <div class="top-vid-meta">
        <div class="top-vid-title">${v.title}</div>
        <div class="top-vid-stats">
          <div class="top-vid-stat"><div class="top-vid-stat-val">${fmt(v.views)}</div><div class="top-vid-stat-lbl">Views</div></div>
          <div class="top-vid-stat"><div class="top-vid-stat-val">${fmt(v.likes)}</div><div class="top-vid-stat-lbl">Likes</div></div>
          <div class="top-vid-stat"><div class="top-vid-stat-val">${v.engagement}%</div><div class="top-vid-stat-lbl">Engagement</div></div>
          <div class="top-vid-stat"><div class="top-vid-stat-val">${v.dur_fmt}</div><div class="top-vid-stat-lbl">Duration</div></div>
        </div>
      </div>
    </div>`;
}

async function load(showSpinner=true) {
  if (showSpinner) { $('loader').style.display='flex'; $('home-data').style.display='none'; }
  $('refresh-btn').classList.add('spinning');
  try {
    const d = await fetch('/api/stats').then(r=>r.json());
    if (d.error) {
      $('error-area').innerHTML=`<div class="error-banner">⚠ ${d.error}</div>`;
      $('loader').style.display='none'; $('home-data').style.display='block'; return;
    }
    $('error-area').innerHTML='';
    channelData = d;

    $('ch-avatar').src=d.thumbnail;
    $('ch-name').textContent=d.title;
    $('ch-meta').textContent=[d.country, d.created?'Since '+d.created:''].filter(Boolean).join(' · ');
    $('ch-time').textContent='Updated '+d.fetched_at;
    $('live-indicator').style.display=d.is_live?'block':'none';

    $('kpi-strip').innerHTML=[
      {icon:'fa-users',     label:'Subscribers',    val:d.subs,             sub:'total'},
      {icon:'fa-eye',       label:'Total Views',     val:d.total_views,      sub:'all time'},
      {icon:'fa-video',     label:'Videos',          val:d.total_videos,     sub:'uploaded'},
      {icon:'fa-chart-bar', label:'Avg Views',       val:d.avg_views||0,     sub:'recent 50'},
      {icon:'fa-thumbs-up', label:'Recent Likes',    val:d.total_likes||0,   sub:'last 50 vids'},
      {icon:'fa-comment',   label:'Recent Comments', val:d.total_comments||0,sub:'last 50 vids'},
    ].map(k=>`<div class="kpi"><div class="kpi-icon"><i class="fa ${k.icon}"></i></div><div class="kpi-label">${k.label}</div><div class="kpi-value">${fmt(k.val)}</div><div class="kpi-sub">${k.sub}</div></div>`).join('');

    allVideos=d.videos||[];
    renderTopVid(d.top_video);
    renderChart(allVideos);

    const recent=[...allVideos].sort((a,b)=>b.published.localeCompare(a.published)).slice(0,6);
    $('recent-tag').textContent=recent.length+' shown';
    $('grid-recent').innerHTML=recent.length?recent.map(vcard).join(''):'<div class="empty">No videos yet</div>';

    const shorts=d.shorts||[];
    $('shorts-tag').textContent=shorts.length+' found';
    $('grid-shorts').innerHTML=shorts.length?shorts.slice(0,6).map(vcard).join(''):'<div class="empty">No Shorts found</div>';

    filterVideos();

    $('about-banner').src=d.banner||d.thumbnail;
    $('about-desc').textContent=d.description||'No description available.';
    $('about-stats').innerHTML=[
      {label:'Subscribers',val:fmt(d.subs)},{label:'Total Views',val:fmt(d.total_views)},
      {label:'Total Videos',val:d.total_videos},{label:'Country',val:d.country||'—'},{label:'Joined',val:d.created||'—'},
    ].map(s=>`<div class="about-stat"><div class="about-stat-label">${s.label}</div><div class="about-stat-value">${s.val}</div></div>`).join('');

    $('loader').style.display='none'; $('home-data').style.display='block';
  } catch(e) {
    $('loader').style.display='none'; $('home-data').style.display='block';
    $('error-area').innerHTML=`<div class="error-banner">⚠ ${e.message}</div>`;
  } finally {
    $('refresh-btn').classList.remove('spinning');
  }
}
function reload() { load(false); }

function switchTab(name, btn) {
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('show'));
  document.querySelectorAll('.tb-btn').forEach(b=>b.classList.remove('on'));
  $('tab-'+name).classList.add('show'); btn.classList.add('on');
}
function openVid(id, title) {
  $('modal-title').textContent=title;
  $('vid-frame').src=`https://www.youtube.com/embed/${id}?autoplay=1`;
  $('vid-overlay').classList.add('open');
}
function closeVid() { $('vid-overlay').classList.remove('open'); $('vid-frame').src=''; }
$('vid-overlay').addEventListener('click',e=>{if(e.target===$('vid-overlay'))closeVid();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeVid();});


// ══════════════════════════════════════════════
//  OFFLINE CHANNEL ADVISOR — no AI, no internet
// ══════════════════════════════════════════════
let advOpen = false;

const TOPICS = [
  { icon:'📊', title:'How is my channel doing?',       sub:'Overall health snapshot',          fn: answerOverall },
  { icon:'🏆', title:'What is my best video?',         sub:'Top performer breakdown',          fn: answerTopVideo },
  { icon:'👁️', title:'Why are my views low?',          sub:'View count analysis & causes',    fn: answerViews },
  { icon:'💬', title:'How is my engagement?',          sub:'Likes, comments & rate',          fn: answerEngagement },
  { icon:'⚡', title:'Should I post more Shorts?',     sub:'Shorts vs long-form stats',       fn: answerShorts },
  { icon:'📅', title:'How often am I uploading?',      sub:'Frequency & consistency check',   fn: answerFrequency },
  { icon:'📈', title:'Am I growing or declining?',     sub:'Recent vs older video trend',     fn: answerGrowth },
  { icon:'🎬', title:'What video format works best?',  sub:'Duration & format performance',   fn: answerFormat },
];

function toggleAdvisor() {
  advOpen = !advOpen;
  $('adv-panel').classList.toggle('open', advOpen);
  if (advOpen) showHome();
}

function showHome() {
  if (!channelData) {
    $('adv-body').innerHTML=`<div style="font-family:var(--mono);font-size:.63rem;color:var(--muted);text-align:center;padding:2rem 1rem;line-height:1.7;">Channel data not loaded yet.<br>Wait for the page to finish loading.</div>`;
    return;
  }
  $('adv-body').innerHTML=`
    <div class="adv-home">
      <div class="adv-intro">Pick any question below — answers come directly from <strong>${channelData.title}</strong>'s real numbers. No internet or AI needed.</div>
      ${TOPICS.map((t,i)=>`
        <button class="topic-btn" onclick="showAnswer(${i})">
          <span class="topic-icon">${t.icon}</span>
          <span class="topic-text"><span class="t-title">${t.title}</span><span class="t-sub">${t.sub}</span></span>
          <i class="fa fa-chevron-right topic-arr"></i>
        </button>`).join('')}
    </div>`;
}

function showAnswer(i) {
  const d = channelData;
  const topic = TOPICS[i];
  const html = topic.fn(d);
  $('adv-body').innerHTML=`
    <div class="adv-answer">
      <button class="back-btn" onclick="showHome()"><i class="fa fa-arrow-left"></i> All Questions</button>
      <div class="answer-title">${topic.icon} ${topic.title}</div>
      <div class="answer-body">${html}</div>
    </div>`;
}

// helpers
function statRow(items) {
  return `<div class="stat-row">${items.map(i=>`<div class="stat-box"><div class="stat-box-val">${i.val}</div><div class="stat-box-lbl">${i.lbl}</div></div>`).join('')}</div>`;
}
function tip(text) {
  return `<div class="tip-box"><div class="tip-lbl">💡 Tip</div>${text}</div>`;
}

// ── 1. Overall
function answerOverall(d) {
  const vpp = d.total_videos > 0 ? Math.round(d.total_views/d.total_videos) : 0;
  const subsOk = d.subs >= 1000;
  const viewsOk = (d.avg_views||0) >= 500;
  return `
    ${statRow([
      {val:fmt(d.subs),         lbl:'Subscribers'},
      {val:fmt(d.total_views),  lbl:'Total Views'},
      {val:fmt(d.avg_views||0), lbl:'Avg Views'},
      {val:d.total_videos,      lbl:'Total Videos'},
    ])}
    <p>Your channel <strong>${d.title}</strong> has <span class="${subsOk?'clr-good':'clr-warn'}">${fmt(d.subs)} subscribers</span> and <strong>${fmt(d.total_views)}</strong> total views across <strong>${d.total_videos}</strong> videos.</p><br>
    <p>Average views per video (all time): <strong>${fmt(vpp)}</strong>.<br>
    Average views in your recent 50 videos: <span class="${viewsOk?'clr-good':'clr-warn'}">${fmt(d.avg_views||0)}</span>. ${viewsOk?'That\'s decent.':'Below 500 — focus on thumbnails and titles first.'}</p><br>
    ${d.is_live?'<p><span class="clr-red">🔴 You are LIVE right now!</span></p><br>':''}
    ${tip('The biggest lever for small channels is <strong>click-through rate (CTR)</strong>. A better thumbnail gets you more views from the same number of impressions.')}`;
}

// ── 2. Top video
function answerTopVideo(d) {
  const v = d.top_video;
  if (!v) return '<p>Not enough video data yet.</p>';
  const videos = d.videos||[];
  const byEng  = [...videos].sort((a,b)=>b.engagement-a.engagement)[0];
  return `
    ${statRow([
      {val:fmt(v.views),    lbl:'Views'},
      {val:fmt(v.likes),    lbl:'Likes'},
      {val:fmt(v.comments), lbl:'Comments'},
      {val:v.engagement+'%',lbl:'Engagement'},
    ])}
    <p><strong>Most-viewed:</strong> <span class="clr-red">${v.title}</span></p>
    <p style="margin-top:.35rem">Published <strong>${v.published}</strong> &nbsp;·&nbsp; Duration <strong>${v.dur_fmt}</strong></p>
    ${byEng && byEng.id!==v.id?`<br><p><strong>Highest engagement rate:</strong> <span class="clr-good">${byEng.title.slice(0,50)}</span> at <span class="clr-good">${byEng.engagement}%</span></p>`:''}
    <br>${tip(`Study what made your top video work — its thumbnail style, title wording, topic. Repeat that formula in your next 3 uploads.`)}`;
}

// ── 3. Views
function answerViews(d) {
  const avg  = d.avg_views||0;
  const subs = d.subs||1;
  const ratio = +(avg/subs*100).toFixed(1);
  let diagnosis;
  if (ratio < 3)       diagnosis = `<span class="clr-warn">Only ${ratio}% of your subs watch each video.</span> Work hard on titles & thumbnails — this is the main issue.`;
  else if (ratio < 15) diagnosis = `<span class="clr-good">${ratio}% of subs watch per video</span> — decent reach. Keep improving your thumbnail CTR.`;
  else                 diagnosis = `<span class="clr-good">${ratio}% reach</span> — great! Your subscribers are engaged. Focus on growing subs now.`;

  const recent5 = [...(d.videos||[])].sort((a,b)=>b.published.localeCompare(a.published)).slice(0,5);
  const r5avg   = recent5.length?Math.round(recent5.reduce((s,v)=>s+v.views,0)/recent5.length):0;
  return `
    ${statRow([
      {val:fmt(avg),    lbl:'Avg Views'},
      {val:ratio+'%',   lbl:'Sub Reach %'},
      {val:fmt(r5avg),  lbl:'Last 5 Avg'},
      {val:fmt(subs),   lbl:'Subscribers'},
    ])}
    <p>${diagnosis}</p><br>
    <p>Your last 5 videos averaged <strong>${fmt(r5avg)}</strong> views. ${r5avg>=avg?'<span class="clr-good">Better than your overall average ↑</span>':'<span class="clr-warn">Below your overall average ↓</span>'}</p><br>
    <p><strong>Top reasons views are low:</strong></p>
    <ul class="ans-list">
      <li>Weak thumbnail — the #1 reason for low views</li>
      <li>Title has no hook or keyword</li>
      <li>Posting inconsistently — algorithm slows you down</li>
      <li>Wrong upload time for your audience</li>
      <li>Not promoting on Shorts or other platforms</li>
    </ul>
    ${tip('Redesign the thumbnails on your 5 least-viewed videos. Better thumbnails on old videos can revive them without any new content.')}`;
}

// ── 4. Engagement
function answerEngagement(d) {
  const videos = d.videos||[];
  const avgEng = videos.length?(videos.reduce((s,v)=>s+v.engagement,0)/videos.length).toFixed(2):0;
  const topEng = [...videos].sort((a,b)=>b.engagement-a.engagement).slice(0,3);
  const good   = parseFloat(avgEng)>=2;
  return `
    ${statRow([
      {val:avgEng+'%',             lbl:'Avg Engagement'},
      {val:fmt(d.total_likes||0),  lbl:'Total Likes'},
      {val:fmt(d.total_comments||0),lbl:'Total Comments'},
      {val:fmt(d.avg_views||0),    lbl:'Avg Views'},
    ])}
    <p>Average engagement across your recent videos: <span class="${good?'clr-good':'clr-warn'}">${avgEng}%</span>. ${good?'That\'s healthy — YouTube considers 2%+ strong.':'Below 2%. Ask viewers to like & comment at the end of each video.'}</p><br>
    <p><strong>Your 3 most engaging videos:</strong></p>
    <ul class="ans-list">
      ${topEng.map(v=>`<li><strong>${v.engagement}%</strong> — ${v.title.slice(0,52)}${v.title.length>52?'…':''}</li>`).join('')}
    </ul>
    ${tip('End every video with a specific question. "What do YOU think about X? Comment below." This alone can 2–3× your comment count.')}`;
}

// ── 5. Shorts
function answerShorts(d) {
  const shorts = d.shorts||[];
  const longs  = (d.videos||[]).filter(v=>!v.is_short);
  const sAvg   = shorts.length?Math.round(shorts.reduce((s,v)=>s+v.views,0)/shorts.length):0;
  const lAvg   = longs.length ?Math.round(longs.reduce((s,v)=>s+v.views,0)/longs.length) :0;
  return `
    ${statRow([
      {val:shorts.length,lbl:'Your Shorts'},
      {val:longs.length, lbl:'Long Videos'},
      {val:fmt(sAvg),    lbl:'Short Avg Views'},
      {val:fmt(lAvg),    lbl:'Long Avg Views'},
    ])}
    ${shorts.length===0
      ?`<p><span class="clr-warn">You have zero Shorts.</span> Shorts can expose you to millions of new viewers with almost no extra production cost.</p>`
      :`<p>Your Shorts average <strong>${fmt(sAvg)}</strong> views vs <strong>${fmt(lAvg)}</strong> for long videos. ${sAvg>=lAvg?'<span class="clr-good">Shorts are outperforming — make more!</span>':'Long videos outperform your Shorts, but Shorts still help discovery.'}</p>`
    }<br>
    <p><strong>Should you post more Shorts?</strong></p>
    <ul class="ans-list">
      <li>${shorts.length<5?'<span class="clr-warn">Yes — you barely have any.</span> Even 2 Shorts/week can spike your impressions.':sAvg>=lAvg?'<span class="clr-good">Yes</span> — your Shorts are already outperforming.':'Yes — Shorts bring discovery even if views are smaller.'}</li>
      <li>Shorts convert viewers: people discover you via Shorts, then watch your long videos</li>
      <li>Best tactic: clip your best long-video moments into Shorts</li>
    </ul>
    ${tip('Post 1 Short per 2 long videos. Hook in the first 2 seconds — skip all intros on Shorts.')}`;
}

// ── 6. Frequency
function answerFrequency(d) {
  const vids = [...(d.videos||[])].sort((a,b)=>b.published.localeCompare(a.published));
  const gaps  = [];
  for (let i=0;i<Math.min(vids.length-1,10);i++) {
    const diff = (new Date(vids[i].published)-new Date(vids[i+1].published))/(864e5);
    gaps.push(Math.round(diff));
  }
  const avgGap = gaps.length?Math.round(gaps.reduce((s,g)=>s+g,0)/gaps.length):null;
  const last   = vids[0];
  const daysSince = last?Math.round((Date.now()-new Date(last.published))/(864e5)):null;

  let freqLabel='—', freqClr='clr-warn';
  if (avgGap!==null){
    if (avgGap<=3)       {freqLabel='Every few days';      freqClr='clr-good';}
    else if (avgGap<=8)  {freqLabel='About weekly';        freqClr='clr-good';}
    else if (avgGap<=16) {freqLabel='Every 1–2 weeks';     freqClr='clr-warn';}
    else                 {freqLabel='Infrequent ('+avgGap+'d avg)'; freqClr='clr-warn';}
  }
  return `
    ${statRow([
      {val:avgGap!==null?avgGap+'d':'—',         lbl:'Avg Gap'},
      {val:daysSince!==null?daysSince+'d ago':'—',lbl:'Last Upload'},
      {val:freqLabel,                            lbl:'Pace'},
      {val:d.total_videos,                       lbl:'Total Videos'},
    ])}
    <p>Your upload pace: <span class="${freqClr}">${freqLabel}</span>.</p><br>
    ${daysSince!==null&&daysSince>14?`<p><span class="clr-warn">⚠ ${daysSince} days since your last upload.</span> The algorithm is likely already pushing you less. Upload ASAP.</p><br>`:''}
    <p><strong>Ideal cadence by channel size:</strong></p>
    <ul class="ans-list">
      <li>Under 1K subs — 3–5×/week to build momentum</li>
      <li>1K–10K subs — at least 1–2×/week</li>
      <li>10K+ subs — 1×/week long + Shorts to stay visible</li>
    </ul>
    ${tip('Consistency > quality when starting out. One solid video every week beats one perfect video per month.')}`;
}

// ── 7. Growth trend
function answerGrowth(d) {
  const vids = [...(d.videos||[])].sort((a,b)=>b.published.localeCompare(a.published));
  const r5   = vids.slice(0,5), o5 = vids.slice(5,10);
  const rAvg = r5.length?Math.round(r5.reduce((s,v)=>s+v.views,0)/r5.length):0;
  const oAvg = o5.length?Math.round(o5.reduce((s,v)=>s+v.views,0)/o5.length):0;
  const pct  = oAvg>0?Math.round((rAvg-oAvg)/oAvg*100):null;
  const up   = rAvg>=oAvg;
  return `
    ${statRow([
      {val:fmt(rAvg),lbl:'Last 5 Avg'},
      {val:fmt(oAvg),lbl:'Prev 5 Avg'},
      {val:pct!==null?(pct>=0?'+':'')+pct+'%':'—',lbl:'Change'},
      {val:fmt(d.subs),lbl:'Subscribers'},
    ])}
    <p>Last 5 videos averaged <strong>${fmt(rAvg)}</strong> views. Previous 5 averaged <strong>${fmt(oAvg)}</strong>.</p><br>
    ${pct!==null?`<p>That's a <span class="${up?'clr-good':'clr-warn'}">${pct>=0?'+':''}${pct}% ${up?'increase ↑':'decrease ↓'}</span> in average views.</p><br>`:''}
    <p><strong>Recent top 3 uploads:</strong></p>
    <ul class="ans-list">
      ${r5.slice(0,3).map(v=>`<li><strong>${fmt(v.views)}</strong> views — ${v.title.slice(0,50)}${v.title.length>50?'…':''}</li>`).join('')}
    </ul>
    ${tip(up
      ?'You\'re trending up! Double down on whatever your recent videos have in common — topic, style, or thumbnail design.'
      :'Views are dipping. Try a different thumbnail style, a more trending topic, or a stronger hook in the first 30 seconds.')}`;
}

// ── 8. Format
function answerFormat(d) {
  const videos = d.videos||[];
  const shorts = videos.filter(v=>v.is_short);
  const mid    = videos.filter(v=>!v.is_short&&v.dur_sec<=600);
  const long   = videos.filter(v=>!v.is_short&&v.dur_sec>600);
  const avg    = arr=>arr.length?Math.round(arr.reduce((s,v)=>s+v.views,0)/arr.length):0;
  const formats = [
    {lbl:'Shorts (≤60s)',  cnt:shorts.length, avg:avg(shorts)},
    {lbl:'Mid (1–10 min)', cnt:mid.length,    avg:avg(mid)},
    {lbl:'Long (10min+)',  cnt:long.length,   avg:avg(long)},
  ].sort((a,b)=>b.avg-a.avg);
  return `
    ${statRow([
      {val:shorts.length+' · '+fmt(avg(shorts)), lbl:'Shorts avg views'},
      {val:mid.length+' · '+fmt(avg(mid)),       lbl:'Mid avg views'},
      {val:long.length+' · '+fmt(avg(long)),     lbl:'Long avg views'},
    ])}
    <p><strong>Ranked by average views:</strong></p>
    <ul class="ans-list">
      ${formats.map((f,i)=>`<li>${['🥇','🥈','🥉'][i]} <strong>${f.lbl}</strong> — ${fmt(f.avg)} avg views (${f.cnt} videos)</li>`).join('')}
    </ul><br>
    <p>${formats[0].cnt===0
      ?`<span class="clr-warn">Not enough ${formats[0].lbl} videos to judge. Try a few to test.`
      :`<span class="clr-good">${formats[0].lbl}</span> performs best on your channel. Make more of those.`
    }</p>
    ${tip('Put 70% of your effort into your best-performing format, 30% into testing new formats.')}`;
}

load();
setInterval(()=>load(false), 120_000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    missing = []
    if YOUTUBE_API_KEY == "YOUR_YOUTUBE_API_KEY": missing.append("YOUTUBE_API_KEY")
    if CHANNEL_ID      == "YOUR_CHANNEL_ID":      missing.append("CHANNEL_ID")

    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║      YT Analytics Pro  🚀            ║")
    print("  ╠══════════════════════════════════════╣")
    print("  ║  http://127.0.0.1:5000               ║")
    print("  ╚══════════════════════════════════════╝")
    if missing:
        print()
        print(f"  ⚠  Open yt.py and set: {', '.join(missing)}")
    print()
    app.run(debug=True, port=5000)
