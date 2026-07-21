#!/usr/bin/env python3
"""Self-contained usage-dashboard renderer (inline CSS/JS/SVG, no CDN/deps).

No gi/GTK: pulls its pure inputs from core and returns an HTML string that
claude-monitor.py atomic-writes to DASH_PATH. Exercised by --selfcheck.
"""

import base64
import os

from .core import (
    _embed_json,
    despike,
    heatmap_buckets,
    history_numeric,
    latest_state,
    reset_marks,
    usage7_series,
    with_gaps,
)

# Derived cache file, so it lives under the XDG cache dir, not ~/.claude/.
DASH_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "claude-tray"
)
DASH_PATH = os.path.join(DASH_DIR, "dashboard.html")


DASH_INTERVAL = 5 * 60  # dashboard-regen throttle in poll_loop (seconds)
# The page is a static file, so an open tab would otherwise never update. ponytail:
# meta-refresh over a JS poller.
_DASH_META_REFRESH = f"<meta http-equiv=\"refresh\" content=\"{DASH_INTERVAL}\">"


# --- Dashboard HTML (self-contained: inline CSS/JS, SVG charts, no CDN/deps) ---
# Its one http:// is the SVG namespace passed to createElementNS: an identifier, never
# fetched. No <link, no src=, no https:// -- --selfcheck asserts all of that.
def _brand_icon_uri():
    """base64 data: URI for the installed Claude icon, or "" when absent. Embedded, and
    applied via CSS background-image, because the page may carry no `src=` (see above).
    """
    for p in (
        "/usr/share/icons/hicolor/32x32/apps/claude-desktop.png",
        "/usr/share/icons/hicolor/48x48/apps/claude-desktop.png",
    ):
        try:
            with open(p, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            return "data:image/png;base64," + data
        except OSError:
            continue
    return ""


_BRAND_URI = _brand_icon_uri()

_BRAND_CSS = (
    (
        "#brand{width:20px;height:20px;display:inline-block;flex:none;"
        "margin-right:.45em;background-size:contain;background-repeat:no-repeat;"
        "background-position:center;background-image:url(" + _BRAND_URI + ")}"
    )
    if _BRAND_URI
    else "#brand{display:none}"
)

# One string, so the [data-theme=dark] rule and the prefers-color-scheme fallback that
# both interpolate it cannot drift apart.
_DASH_DARK = (
    "--bg:#16181d;--fg:#e6e8ec;--card:#1e2128;--border:#2c313a;--muted:#8b929c;"
    "--accent:#4a9eda;--accent2:#e0a458;--mark:#4a5261;--grid:#3a414b;"
    "--gridlite:#2a2f37;--h2:#cfd3da;"
    "--btn:#252932;--btnbd:#3a414b;--legend:#9aa1ab;--swbd:#3a414b;"
    "--shadow:rgba(0,0,0,.35)"
)

_DASH_STYLE = (
    ":root{--bg:#f4f5f7;--fg:#1a1a1a;--card:#fff;--border:#e6e6e6;--muted:#888;"
    "--accent:#1a6cae;--accent2:#c2670f;--mark:#c9ccd1;--grid:#ccc;"
    "--gridlite:#eee;--h2:#333;--btn:#fff;"
    "--btnbd:#bbb;--legend:#555;--swbd:#ddd;--shadow:rgba(0,0,0,.06)}"
    "[data-theme=\"dark\"]{" + _DASH_DARK + "}"
    "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){"
    + _DASH_DARK + "}}"
    "body{font-family:sans-serif;background:var(--bg);color:var(--fg);"
    "max-width:920px;margin:0 auto;padding:1.5em}"
    "h1{font-size:1.3em;margin:.2em 0;display:flex;align-items:center;"
    "justify-content:space-between}"
    "h2{font-size:1em;color:var(--h2);margin:0 0 .6em}"
    "section{background:var(--card);border:1px solid var(--border);"
    "border-radius:8px;padding:.9em 1.1em;margin:0 0 1.1em;"
    "box-shadow:0 1px 3px var(--shadow)}"
    "svg{max-width:100%;height:auto}"
    "svg .grid{stroke:var(--grid)}svg .gridlite{stroke:var(--gridlite)}"
    "svg .axis{fill:var(--muted)}"
    "svg .series{stroke:var(--accent);fill:none;stroke-width:2}"
    "svg .series7{stroke:var(--accent2);fill:none;stroke-width:2}"
    "svg .reset{stroke:var(--mark);stroke-dasharray:3 3}"
    "svg .dot{fill:var(--accent);stroke:none}"
    "svg .dot7{fill:var(--accent2);stroke:none}"
    "svg .proj{stroke:var(--accent);stroke-dasharray:4 3;fill:none;"
    "stroke-width:2;opacity:.75}"
    "svg .proj7{stroke:var(--accent2);stroke-dasharray:4 3;fill:none;"
    "stroke-width:2;opacity:.75}"
    "svg .proj.over,svg .proj7.over{stroke:#d1495b;opacity:.95}"
    "svg .projlab{fill:var(--accent);font-size:11px;font-weight:600}"
    "svg .projlab7{fill:var(--accent2);font-size:11px;font-weight:600}"
    "svg .projlab.over,svg .projlab7.over{fill:#d1495b}"
    "#u-legend .kp{background:repeating-linear-gradient(90deg,"
    "var(--accent) 0 4px,transparent 4px 7px)}"
    "#status{display:flex;flex-direction:column;gap:.55em}"
    ".srow{display:grid;grid-template-columns:5em 3.2em 7em 1fr;align-items:center;"
    "gap:.6em;font-size:.9em}"
    ".sname{font-weight:600;display:flex;align-items:center}"
    ".sval{text-align:right;font-variant-numeric:tabular-nums}"
    ".sbar{height:8px;background:var(--gridlite);border-radius:4px;"
    "overflow:hidden;display:block}"
    ".sfill{display:block;height:100%;background:var(--accent);border-radius:4px}"
    ".sfill.hot{background:#d1495b}"
    ".smeta{color:var(--muted);font-size:.9em}"
    "#u-legend{display:flex;align-items:center;gap:.4em;font-size:.85em;"
    "color:var(--legend);margin-top:.4em}"
    "#u-legend .k{width:14px;height:3px;display:inline-block;vertical-align:middle}"
    "#u-legend .k5{background:var(--accent)}"
    "#u-legend .k7{background:var(--accent2)}"
    "#u-legend .kr{background:var(--mark)}"
    "#ranges button,#theme{padding:.25em .8em;border:1px solid var(--btnbd);"
    "background:var(--btn);color:var(--fg);border-radius:4px;cursor:pointer;"
    "font:inherit}"
    "#ranges button{margin-right:.4em}"
    "#theme{font-size:.7em}"
    "#ranges button.active{background:var(--accent);color:#fff;"
    "border-color:var(--accent)}"
    "#usage-now{color:var(--accent);font-weight:600}"
    "p.empty{color:var(--muted)}"
    "#sess-tbl{width:100%;border-collapse:collapse;font-size:.9em}"
    "#sess-tbl th{color:var(--muted);text-align:left;font-weight:600;"
    "padding:.3em .4em}"
    "#sess-tbl td{border-top:1px solid var(--border);padding:.3em .4em}"
    ".sd{width:.7em;height:.7em;border-radius:50%;display:inline-block;"
    "margin-right:.45em;vertical-align:middle}"
    ".sd-waiting{background:var(--accent2)}"
    ".sd-running{background:var(--accent)}"
    ".sd-done{background:var(--muted)}"
    ".sess-done{opacity:.5}"
    ".sdur{text-align:right;font-variant-numeric:tabular-nums}"
    "#meta{color:var(--muted);font-size:.85em;margin:.2em 0 1.5em}"
    "#hm-legend{display:flex;align-items:center;gap:.4em;font-size:.85em;"
    "color:var(--legend);margin-top:.5em}"
    "#hm-legend .sw{width:16px;height:12px;display:inline-block;"
    "border:1px solid var(--swbd);vertical-align:middle}"
    # currentColor so glyphs theme for free; no xmlns, which inline SVG does not need.
    ".ic{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.5;"
    "stroke-linecap:round;stroke-linejoin:round;vertical-align:-2px;"
    "margin-right:.35em;flex:none}"
    "h2 .ic{opacity:.75}"
    ".ttl{display:flex;align-items:center;min-width:0}"
    + _BRAND_CSS
)

_IC_GAUGE = (  # no xmlns on purpose -- see .ic above
    "<svg class=\"ic\" viewBox=\"0 0 16 16\">"
    "<path d=\"M2 12a6 6 0 1 1 12 0\"/><path d=\"M8 12l3.5-3.5\"/></svg>"
)
_IC_TREND = (
    "<svg class=\"ic\" viewBox=\"0 0 16 16\">"
    "<path d=\"M2 13V3\"/><path d=\"M2 13h12\"/><path d=\"M4 10l3-3 2.5 2.5L14 5\"/></svg>"
)
_IC_GRID = (
    "<svg class=\"ic\" viewBox=\"0 0 16 16\">"
    "<path d=\"M2.5 2.5h11v11h-11z\"/><path d=\"M6 2.5v11\"/><path d=\"M10 2.5v11\"/>"
    "<path d=\"M2.5 6h11\"/><path d=\"M2.5 10h11\"/></svg>"
)

_DASH_EMPTY = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    + _DASH_META_REFRESH +
    "<title>Claude Code - Usage Dashboard</title>"
    "<style>" + _DASH_STYLE + "</style></head>"
    "<body><h1><span class=\"ttl\"><span id=\"brand\"></span>"
    "Claude Code - Usage Dashboard</span></h1>"
    "<p class=\"empty\">Collecting usage history...</p></body></html>"
)

_DASH_BODY = (
    "<h1><span class=\"ttl\"><span id=\"brand\"></span>"
    "Claude Code - Usage Dashboard</span>"
    "<button id=\"theme\">Dark</button></h1>"
    "<div id=\"meta\"></div>"
    "<section><h2>Sessions</h2>"
    "<table id=\"sess-tbl\"><thead><tr>"
    "<th>Project</th><th>Status</th><th>Duration</th></tr></thead>"
    "<tbody id=\"sessions\"></tbody></table></section>"
    "<section><h2>" + _IC_GAUGE + "Current quota</h2>"
    "<div id=\"status\"></div></section>"
    "<section><h2>" + _IC_TREND + "Usage % over time"
    "<span id=\"usage-now\"></span></h2>"
    "<div id=\"ranges\"><button data-range=\"h24\">24h</button>"
    "<button data-range=\"d7\">7d</button>"
    "<button data-range=\"all\" class=\"active\">All</button></div>"
    "<svg id=\"usage-chart\" viewBox=\"0 0 600 200\"></svg>"
    "<div id=\"u-legend\"><span class=\"k k5\"></span><span>5-hour</span>"
    "<span class=\"k k7\"></span><span>weekly</span>"
    "<span class=\"k kp\"></span><span>projected</span>"
    "<span class=\"k kr\"></span><span>window reset</span></div></section>"
    "<section><h2>" + _IC_GRID + "Usage by hour (mean % of the 5h cap)</h2>"
    "<svg id=\"heatmap\" viewBox=\"0 0 520 170\"></svg>"
    "<div id=\"hm-legend\"></div></section>"
)

_DASH_JS = """
var NS="http://www.w3.org/2000/svg";
// Declared up here on purpose: drawUsage() runs during init and reads WIN5 for the
// projection. Left further down (beside the status card) `var` hoisting would give
// it the name but not the value -- WIN5 would be undefined at first paint.
var WIN5=18000,WIN7=604800;
var DAYS=["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
function clear(n){while(n.firstChild)n.removeChild(n.firstChild);}
function el(name,attrs){var e=document.createElementNS(NS,name);for(var k in attrs)e.setAttribute(k,attrs[k]);return e;}
function two(n){return(n<10?"0":"")+n;}
function drawChart(svg,seriesList,marks,unit,yfloor,projs){
  var W=600,H=200,PL=42,PR=12,PT=12,PB=30,xs=[],ys=[];
  seriesList.forEach(function(s){s.pts.forEach(function(p){
    if(p[1]!==null){xs.push(p[0]);ys.push(p[1]);}});});
  if(!xs.length)return;
  // A "to" projection lands in the FUTURE (the 5h reset), so widen the domain to
  // include it or it would be drawn off the right edge. "rate" projections are
  // deliberately NOT included -- see the note where they are drawn.
  (projs||[]).forEach(function(pr){
    if(pr.kind==="to"){xs.push(pr.t1);ys.push(pr.p1);}
  });
  var xmin=Math.min.apply(null,xs),xmax=Math.max.apply(null,xs);
  var ymax=Math.max.apply(null,ys);if(ymax<yfloor)ymax=yfloor;if(ymax<=0)ymax=1;
  var xr=(xmax-xmin)||1,spanDays=xr/86400,i,yv,xv,gy,gx,t;
  function sx(x){return PL+(x-xmin)/xr*(W-PL-PR);}
  function sy(y){return H-PB-(y/ymax)*(H-PB-PT);}
  function xlab(xv){var dt=new Date(xv*1000);return spanDays<2?(dt.getHours()+":"+two(dt.getMinutes())):((dt.getMonth()+1)+"/"+dt.getDate());}
  for(i=0;i<=4;i++){
    yv=ymax*i/4;gy=sy(yv);
    svg.appendChild(el("line",{x1:PL,y1:gy,x2:W-PR,y2:gy,"class":i?"gridlite":"grid"}));
    t=el("text",{x:PL-5,y:gy+4,"font-size":11,"text-anchor":"end","class":"axis"});
    t.textContent=(ymax>=10?Math.round(yv):yv.toFixed(1))+(unit||"");svg.appendChild(t);
  }
  for(i=0;i<=4;i++){
    xv=xmin+xr*i/4;gx=sx(xv);
    svg.appendChild(el("line",{x1:gx,y1:H-PB,x2:gx,y2:H-PB+4,"class":"grid"}));
    t=el("text",{x:gx,y:H-PB+16,"font-size":11,"text-anchor":"middle","class":"axis"});
    t.textContent=xlab(xv);svg.appendChild(t);
  }
  svg.appendChild(el("line",{x1:PL,y1:PT,x2:PL,y2:H-PB,"class":"grid"}));
  // Window-reset markers, drawn UNDER the series: the usage line drops at these
  // instants because the 5h window rolled, not because usage fell. Without them
  // the sawtooth reads as "my usage went down", which is simply false.
  (marks||[]).forEach(function(m){
    if(m<xmin||m>xmax)return;
    var mx=sx(m);
    svg.appendChild(el("line",{x1:mx,y1:PT,x2:mx,y2:H-PB,"class":"reset"}));
  });
  // Projected trajectories. Dashed because they are guesses, not data; red past 100.
  // Two shapes:
  //   kind "to"   - runs to a specific future point (the 5h reset is only hours out,
  //                 so the domain above was widened to include it).
  //   kind "rate" - runs to the chart's right edge at a known %/sec. Used for the
  //                 WEEKLY: its reset is ~4 days out, and stretching the axis that far
  //                 would squash the real history into a sliver, so the line shows the
  //                 slope in view while the LABEL carries the projected-at-reset value.
  (projs||[]).forEach(function(pr){
    var x0=sx(pr.t0),y0=sy(pr.p0),x1,y1;
    if(pr.kind==="rate"){x1=sx(xmax);y1=sy(pr.p0+pr.rate*(xmax-pr.t0));}
    else{x1=sx(pr.t1);y1=sy(pr.p1);}
    svg.appendChild(el("path",{
      d:"M"+x0.toFixed(1)+" "+y0.toFixed(1)+"L"+x1.toFixed(1)+" "+y1.toFixed(1),
      "class":pr.over?(pr.cls+" over"):pr.cls}));
    var lt=el("text",{x:(x1-3).toFixed(1),y:(y1-6).toFixed(1),"font-size":11,
      "text-anchor":"end","class":pr.over?(pr.lcls+" over"):pr.lcls});
    lt.textContent=pr.lab;
    svg.appendChild(lt);
  });
  seriesList.forEach(function(s){
    var d="",pen=false,n=0;
    s.pts.forEach(function(p){if(p[1]!==null)n++;});
    s.pts.forEach(function(p){
      if(p[1]===null){pen=false;return;}
      d+=(pen?"L":"M")+sx(p[0]).toFixed(1)+" "+sy(p[1]).toFixed(1)+" ";pen=true;
    });
    if(d)svg.appendChild(el("path",{d:d,"class":s.cls}));
    // A 1-2 sample series cannot form a line and renders as a stray floating dash.
    // Dot sparse series so a couple of samples read as DATA rather than an artifact.
    if(n<=30&&s.dot){
      s.pts.forEach(function(p){
        if(p[1]===null)return;
        svg.appendChild(el("circle",{cx:sx(p[0]).toFixed(1),cy:sy(p[1]).toFixed(1),
          r:2.5,"class":s.dot}));
      });
    }
  });
}
function drawUsage(range){
  try{localStorage.setItem("ccdash-range",range);}catch(e){}
  var btns=document.querySelectorAll("#ranges button");
  for(var bi=0;bi<btns.length;bi++)btns[bi].classList.toggle("active",btns[bi].getAttribute("data-range")===range);
  var svg=document.getElementById("usage-chart");clear(svg);
  var lo=(range==="h24")?D.bounds.h24:(range==="d7")?D.bounds.d7:-Infinity;
  function f(a){return (a||[]).filter(function(p){return p[0]>=lo;});}
  var marks=(D.resets||[]).filter(function(m){return m>=lo;});
  function lastOf(a){for(var j=a.length-1;j>=0;j--){if(a[j][1]!==null)return a[j];}return null;}
  var u5=f(D.usage),u7=f(D.usage7),projs=[];
  // 5h: reset is only hours away -> project all the way TO it (domain widens to fit).
  var pj5=project(D.now.pct,D.now.reset,WIN5),l5=lastOf(u5);
  if(pj5&&!pj5.early&&l5){
    projs.push({kind:"to",t0:l5[0],p0:l5[1],t1:D.now.reset,p1:pj5.proj,
                over:pj5.proj>100,cls:"proj",lcls:"projlab",
                lab:Math.round(pj5.proj)+"%"});
  }
  // Weekly: reset is ~4 days out. Drawing TO it would stretch the axis 4 days into
  // the future and squash the real history, so run the line at its true %/sec to the
  // chart edge and let the label carry the number that matters (% at the weekly reset).
  var pj7=project(D.now.pct7,D.now.reset7,WIN7),l7=lastOf(u7);
  if(pj7&&!pj7.early&&l7){
    var nowS=Date.now()/1000,start7=D.now.reset7-WIN7;
    var rate7=D.now.pct7/(nowS-start7);
    projs.push({kind:"rate",t0:l7[0],p0:l7[1],rate:rate7,
                over:pj7.proj>100,cls:"proj7",lcls:"projlab7",
                lab:Math.round(pj7.proj)+"% by "+DAYS[new Date(D.now.reset7*1000).getDay()]});
  }
  // yfloor 100: the axis always spans the whole cap, so 22% reads as "plenty of
  // headroom" instead of filling the chart the way an auto-scaled axis would. The
  // 100% gridline already says where the cap is -- no separate "limit" rule needed.
  drawChart(svg,[{pts:u5,cls:"series",dot:"dot"},
                 {pts:u7,cls:"series7",dot:"dot7"}],
            marks,"%",100,projs);
  var bs=document.querySelectorAll("#ranges button");
  for(var i=0;i<bs.length;i++)bs[i].className=(bs[i].getAttribute("data-range")===range)?"active":"";
}
function isDark(){return document.documentElement.getAttribute("data-theme")==="dark";}
function hmFill(val,max){
  // Heatmap cells are data-driven, so they cannot be pure CSS like the rest of the
  // chrome -- the ramp is picked per theme here. Light: pale->dark. Dark: INVERTED
  // (dark->bright), else a low-value cell would glow brightest against a dark page.
  if(val===null)return isDark()?"hsl(220,8%,26%)":"hsl(0,0%,88%)";
  var f=max?val/max:0;
  return isDark()?"hsl(210,75%,"+(20+f*45).toFixed(0)+"%)"
                 :"hsl(210,80%,"+(92-f*62).toFixed(0)+"%)";
}
function hmLegend(max){
  var box=document.getElementById("hm-legend");clear(box);
  function sw(bg){var e=document.createElement("span");e.className="sw";e.style.background=bg;return e;}
  function txt(x){var e=document.createElement("span");e.textContent=x;return e;}
  box.appendChild(txt("Low"));
  box.appendChild(sw(hmFill(max*0.05,max)));
  box.appendChild(sw(hmFill(max*0.5,max)));
  box.appendChild(sw(hmFill(max,max)));
  box.appendChild(txt("High"));
  box.appendChild(sw(hmFill(null,max)));
  box.appendChild(txt("no data"));
}
function drawHeatmap(){
  var svg=document.getElementById("heatmap");clear(svg);
  var g=D.heatmap,max=1,r,c,v;
  for(r=0;r<7;r++)for(c=0;c<24;c++){v=g[r][c];if(v!==null&&v>max)max=v;}
  var days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],cw=20,ch=20,lx=34,ty=18;
  for(c=0;c<24;c+=3){var t=el("text",{x:lx+c*cw+cw/2,y:13,"font-size":12,"text-anchor":"middle","class":"axis"});t.textContent=c;svg.appendChild(t);}
  for(r=0;r<7;r++){
    var lbl=el("text",{x:lx-5,y:ty+r*ch+ch/2+4,"font-size":12,"text-anchor":"end","class":"axis"});
    lbl.textContent=days[r];svg.appendChild(lbl);
    for(c=0;c<24;c++){
      var val=g[r][c],tip;
      if(val===null)tip=days[r]+" "+c+":00 - no data";
      else tip=days[r]+" "+c+":00 - "+val.toFixed(1)+"% quota used (mean/hour)";
      var rect=el("rect",{x:lx+c*cw,y:ty+r*ch,width:cw-1,height:ch-1,fill:hmFill(val,max)});
      var ttl=el("title",{});ttl.textContent=tip;rect.appendChild(ttl);
      svg.appendChild(rect);
    }
  }
  hmLegend(max);
}
var savedRange=null;
try{savedRange=localStorage.getItem("ccdash-range");}catch(e){}
drawUsage(savedRange||"all");drawHeatmap();
var un=D.usage[D.usage.length-1];
document.getElementById("usage-now").textContent=un?(" - now "+Math.round(un[1])+"%"):"";
document.getElementById("meta").textContent="Generated "+new Date(D.generated*1000).toLocaleString();
document.getElementById("ranges").addEventListener("click",function(e){
  var r=e.target.getAttribute("data-range");if(r)drawUsage(r);
});
function setTheme(t){
  document.documentElement.setAttribute("data-theme",t);
  document.getElementById("theme").textContent=(t==="dark")?"Light":"Dark";
  try{localStorage.setItem("ccdash-theme",t);}catch(e){}
  drawHeatmap();
}
var savedTheme=null;
try{savedTheme=localStorage.getItem("ccdash-theme");}catch(e){}
var prefDark=window.matchMedia&&window.matchMedia("(prefers-color-scheme:dark)").matches;
setTheme(savedTheme||(prefDark?"dark":"light"));
document.getElementById("theme").addEventListener("click",function(){
  setTheme(isDark()?"light":"dark");
});
function fmtDur(s){
  s=Math.max(0,Math.floor(s));
  if(s>=86400)return Math.floor(s/86400)+"d "+Math.floor((s%86400)/3600)+"h";
  if(s>=3600)return Math.floor(s/3600)+"h "+Math.floor((s%3600)/60)+"m";
  return Math.floor(s/60)+"m";
}
function hhmm(ep){var d=new Date(ep*1000);return d.getHours()+":"+two(d.getMinutes());}
function project(pct,reset,win){
  // Honest, PERCENTAGE-based projection. claude-monitor ships forecast/status, but
  // both are token-based and report "limit hit" under --api (token counts come back
  // null), so using them would claim you are exhausted at 18%. Instead: the window
  // began at reset-win, so the elapsed fraction is known exactly; extrapolating the
  // current pct linearly over the window gives the projected % at reset, and when
  // that crosses 100 we can say WHEN it would land.
  if(pct===null||pct===undefined||reset===null||reset===undefined)return null;
  var now=Date.now()/1000,start=reset-win,e=(now-start)/win;
  if(e<=0.05)return {early:true};   // barely into the window -> pct/e explodes
  if(e>1)e=1;
  var out={proj:pct/e};
  if(out.proj>100&&pct>0){
    var exh=start+(100/pct)*(now-start);
    if(exh<reset)out.exhaust=exh;
  }
  return out;
}
var IC={
  clock:["M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13z","M8 4.5V8l2.5 1.5"],
  cal:["M2.5 3.5h11v10h-11z","M2.5 6.5h11","M5.5 2v3","M10.5 2v3"]
};
function icon(name){
  // Built with createElementNS (same NS literal the charts use) so the glyph is a
  // real SVG node; .ic strokes it with currentColor, so it themes for free.
  var s=el("svg",{"class":"ic","viewBox":"0 0 16 16"});
  (IC[name]||[]).forEach(function(d){s.appendChild(el("path",{d:d}));});
  return s;
}
function addQuotaRow(box,name,pct,reset,win,ic){
  if(pct===null||pct===undefined)return;
  var now=Date.now()/1000;
  var row=document.createElement("div");row.className="srow";
  function sp(cls,txt){var e=document.createElement("span");e.className=cls;e.textContent=txt;return e;}
  var lab=sp("sname",name);
  if(ic)lab.insertBefore(icon(ic),lab.firstChild);
  row.appendChild(lab);
  row.appendChild(sp("sval",Math.round(pct)+"%"));
  var bar=document.createElement("span");bar.className="sbar";
  var fill=document.createElement("span");
  fill.className=(pct>=80)?"sfill hot":"sfill";
  fill.style.width=Math.min(100,Math.max(0,pct))+"%";
  bar.appendChild(fill);row.appendChild(bar);
  var txt=(reset!==null&&reset!==undefined)?("resets in "+fmtDur(reset-now)):"";
  var p=project(pct,reset,win);
  if(p&&p.exhaust!==undefined)txt+=" - projected to hit 100% at "+hhmm(p.exhaust);
  else if(p&&p.early)txt+=" - too early to project";
  else if(p)txt+=" - on track (projected "+Math.round(p.proj)+"% at reset)";
  row.appendChild(sp("smeta",txt));
  box.appendChild(row);
}
function statusCard(){
  var box=document.getElementById("status");clear(box);
  addQuotaRow(box,"5-hour",D.now.pct,D.now.reset,WIN5,"clock");
  addQuotaRow(box,"Weekly",D.now.pct7,D.now.reset7,WIN7,"cal");
  if(!box.firstChild)box.appendChild(document.createTextNode(
    "No current quota data yet - it appears after the next poll."));
}
statusCard();
// Countdowns and the projection are computed against the LIVE clock, so the card
// stays truthful as this static page ages between the ~5min regenerations.
setInterval(statusCard,20000);
// Sessions panel. Rows are built client-side via textContent from D.sessions so an
// untrusted project dir (arbitrary repo path) can never inject markup (D-08, T-07-01).
var SESS_RANK={waiting:0,running:1,done:2};
function sessDur(s){
  // Under an hour show m+s so the counter visibly ticks each second (D-02); past an
  // hour fall to the coarser fmtDur -- a stale session does not need second precision.
  s=Math.max(0,Math.floor(s));
  if(s>=3600)return fmtDur(s);
  return Math.floor(s/60)+"m "+two(s%60)+"s";
}
function renderSessions(){
  var box=document.getElementById("sessions");
  if(!box)return;
  clear(box);
  var list=(D.sessions||[]).slice();  // guard for an old cached page without the key
  list.sort(function(a,b){
    var ra=SESS_RANK[a.status];if(ra===undefined)ra=99;
    var rb=SESS_RANK[b.status];if(rb===undefined)rb=99;
    return ra-rb;
  });
  if(!list.length){
    var etr=document.createElement("tr"),etd=document.createElement("td");
    etd.setAttribute("colspan","3");
    etd.textContent="No active Claude Code sessions";
    etr.appendChild(etd);box.appendChild(etr);
    return;
  }
  var now=Date.now()/1000;
  list.forEach(function(s){
    var tr=document.createElement("tr");
    if(s.status==="done")tr.className="sess-done";
    var td1=document.createElement("td");td1.textContent=s.dir;tr.appendChild(td1);
    var td2=document.createElement("td");
    var dot=document.createElement("span");dot.className="sd sd-"+s.status;
    td2.appendChild(dot);td2.appendChild(document.createTextNode(s.status));
    tr.appendChild(td2);
    var td3=document.createElement("td");td3.className="sdur";
    // Only a running session ticks live; waiting/done show the frozen run duration so
    // the counter stops climbing once the session stops working (D-02 freeze).
    if(s.status==="running"&&s.entered!==null&&s.entered!==undefined)
      td3.textContent=sessDur(now-s.entered);
    else if(s.frozen!==null&&s.frozen!==undefined)
      td3.textContent=sessDur(s.frozen);
    else
      td3.textContent="-";
    tr.appendChild(td3);
    box.appendChild(tr);
  });
}
renderSessions();
setInterval(renderSessions,1000);
"""


def render_dashboard(records, now, sessions=()):
    """Full self-contained dashboard HTML; the empty-state page when there is no data.
    Range bounds are ROLLING windows (now-24h, now-7d), not calendar ones, which would
    hide the most recent activity right after a reset. `sessions` is a snapshot list of
    {dir,status,entered,frozen} dicts, shipped inert via the _embed_json payload and rendered
    client-side (D-08); it defaults empty so existing callers keep working.
    """
    records = history_numeric(records)
    if not records:
        return _DASH_EMPTY
    payload = {
        "usage": with_gaps(despike([[int(r["t"]), r["pct"]] for r in records])),
        "usage7": with_gaps(despike(usage7_series(records))),
        "resets": reset_marks(records),
        "now": latest_state(records),
        "heatmap": heatmap_buckets(records),
        "bounds": {"h24": int(now - 86400), "d7": int(now - 7 * 86400)},
        "generated": int(now),
        "sessions": list(sessions),
    }
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        + _DASH_META_REFRESH +
        "<title>Claude Code - Usage Dashboard</title>"
        "<style>" + _DASH_STYLE + "</style></head>"
        "<body>" + _DASH_BODY + "<script>const D = " + _embed_json(payload) + ";"
        + _DASH_JS + "</script></body></html>"
    )
