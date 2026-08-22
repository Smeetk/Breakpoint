from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json, os
from urllib.parse import urlparse

PRODUCTS = [
 {"id":"headphones","name":"Auralite Wireless Headphones","category":"Audio","price":2499,"description":"Rich sound, active noise cancellation, and all-day comfort."},
 {"id":"keyboard","name":"Keystack Mechanical Keyboard","category":"Workspace","price":3499,"description":"Tactile hot-swap switches with a compact aluminium frame."},
 {"id":"mouse","name":"Pulse Pro Gaming Mouse","category":"Gaming","price":1499,"description":"A precise lightweight mouse with programmable controls."},
 {"id":"hub","name":"LinkHub USB-C 7-in-1","category":"Accessories","price":1899,"description":"Expand your laptop with HDMI, USB and high-speed card ports."},
 {"id":"stand","name":"Elevate Laptop Stand","category":"Workspace","price":2199,"description":"Adjustable, sturdy and designed for a comfortable eye line."},
 {"id":"watch","name":"Tempo Smart Watch","category":"Wearables","price":4299,"description":"Fitness tracking, notifications and a bright edge-to-edge display."},
 {"id":"speaker","name":"Roomy Bluetooth Speaker","category":"Audio","price":2799,"description":"Portable room-filling sound with 18 hours of battery life."},
 {"id":"webcam","name":"ClearView HD Webcam","category":"Office","price":1999,"description":"Sharp 1080p video and dual microphones for better calls."},
]
state = {"cart": {}, "checkout_snapshot": None}

def payload():
 items=[]
 for pid, qty in state["cart"].items():
  p=next(x for x in PRODUCTS if x["id"]==pid); items.append({**p,"quantity":qty,"lineTotal":p["price"]*qty})
 return {"items":items,"total":sum(x["lineTotal"] for x in items)}

class Handler(SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
 def send_json(self,obj,status=200):
  data=json.dumps(obj).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/api/products': return self.send_json(PRODUCTS)
  if path.startswith('/api/products/'):
   p=next((x for x in PRODUCTS if x['id']==path.rsplit('/',1)[1]),None); return self.send_json(p or {},404 if not p else 200)
  if path=='/api/cart': return self.send_json(payload())
  if path=='/api/checkout':
   if state['checkout_snapshot'] is None: state['checkout_snapshot']=payload()
   return self.send_json(state['checkout_snapshot'])
  return super().do_GET()
 def do_POST(self):
  path=urlparse(self.path).path
  if path=='/api/reset': state['cart'].clear(); state['checkout_snapshot']=None; return self.send_json({'ok':True})
  if path=='/api/cart':
   body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or '{}'); pid=body.get('productId'); state['cart'][pid]=state['cart'].get(pid,0)+int(body.get('quantity',1)); return self.send_json(payload())
  if path=='/api/checkout': state['checkout_snapshot']=payload(); return self.send_json(state['checkout_snapshot'])
  self.send_json({},404)
 def do_PATCH(self):
  path=urlparse(self.path).path
  if path.startswith('/api/cart/'):
   pid=path.rsplit('/',1)[1]; body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or '{}'); qty=max(0,int(body.get('quantity',1)))
   if qty: state['cart'][pid]=qty
   else: state['cart'].pop(pid,None)
   return self.send_json(payload())
  self.send_json({},404)

if __name__=='__main__':
 os.chdir(os.path.dirname(os.path.abspath(__file__))); ThreadingHTTPServer(('0.0.0.0',8000),Handler).serve_forever()
