"""
YT Analytics Pro - Web Hosting Ready
No AI needed — channel advisor runs 100% offline from your stats.

Run locally:
  pip install flask requests
  python yt.py

For Hosting (Render, Railway, Vercel, etc.):
  Set environment variables:
    YOUTUBE_API_KEY=your_actual_key
    CHANNEL_ID=your_channel_id
"""

import os
import re
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

# ═══════════════════════════════════════════════
#  CONFIG — Use Environment Variables (Recommended for Hosting)
# ═══════════════════════════════════════════════
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID      = os.getenv("CHANNEL_ID")

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
    # Check if keys are set
    if not YOUTUBE_API_KEY:
        return {"error": "YOUTUBE_API_KEY environment variable is not set"}
    if not CHANNEL_ID:
        return {"error": "CHANNEL_ID environment variable is not set"}

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

        # Get recent 50 videos
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
        return {"error": f"Error fetching data: {str(exc)}"}


@app.route("/api/stats")
def api_stats():
    return jsonify(get_youtube_stats())


@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "YT Analytics Pro is running"})


@app.route("/")
def index():
    return PAGE


# Keep the entire HTML (PAGE) unchanged — only the Python part was updated
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
/* [Your entire original CSS and HTML remains 100% unchanged] */
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

/* ADVISOR */
.adv-fab{position:fixed;bottom:1.75rem;right:1.75rem;width:54px;height:54px;border-radius:15px;background:linear-gradient(135deg,var(--red),var(--orange));border:none;color:#fff;font-size:1.2rem;cursor:pointer;z-index:300;box-shadow:0 6px 26px rgba(255,45,85,.42);transition:transform .18s,box-shadow .18s;display:flex;align-items:center;justify-content:center;}
.adv-fab:hover{transform:scale(1.08);box-shadow:0 10px 34px rgba(255,45,85,.55);}
.adv-fab-label{position:fixed;bottom:5rem;right:1.75rem;font-family:var(--mono);font-size:.56rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);z-index:300;text-align:center;width:54px;}

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

/* rest of advisor styles */
.adv-intro{font-family:var(--mono);font-size:.61rem;color:var(--muted2);letter-spacing:.03em;margin-bottom:.75rem;line-height:1.65;padding:.65rem .8rem;background:var(--bg3);border-radius:10px;border:1px solid var(--border);}
.adv-home{display:flex;flex-direction:column;gap:.45rem;}
.topic-btn{background:var(--bg3);border:1px solid var(--border2);border-radius:12px;padding:.72rem 1rem;cursor:pointer;text-align:left;color:var(--text);transition:border-color .15s,background .15s;display:flex;align-items:center;gap:.75rem;width:100%;}
.topic-btn:hover{border-color:rgba(255,45,85,.4);background:rgba(255,45,85,.05);}
.topic-btn:active{transform:scale(.98);}
.topic-icon{font-size:1.05rem;width:26px;text-align:center;flex-shrink:0;}
.t-title{font-size:.81rem;font-weight:600;display:block;margin-bottom:.08rem;}
.t-sub{font-family:var(--mono);font-size:.54rem;color:var(--muted);letter-spacing:.03em;}
.topic-arr{color:var(--muted);font-size:.58rem;margin-left:auto;flex-shrink:0;}

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

<!-- [The entire original HTML body remains unchanged] -->
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
  <!-- All the tabs and content remain exactly the same as your original -->
  <!-- ... (I kept it short here for readability, but in your file it should be the full original PAGE) ... -->
</main>

<!-- All JavaScript (including advisor) remains 100% unchanged -->

</body>
</html>
"""

# Note: In the actual file, you should keep your full original PAGE variable.
# I shortened it above for this message. Just replace the Python part.

if __name__ == "__main__":
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║      YT Analytics Pro  🚀            ║")
    print("  ╠══════════════════════════════════════╣")
    print("  ║  Ready for hosting!                  ║")
    print("  ╚══════════════════════════════════════╝")
    print()
    
    if not YOUTUBE_API_KEY or not CHANNEL_ID:
        print("  ⚠  WARNING: Set these environment variables before deploying:")
        print("     YOUTUBE_API_KEY=...")
        print("     CHANNEL_ID=...")
        print()
    
    app.run(debug=True, port=5000)
