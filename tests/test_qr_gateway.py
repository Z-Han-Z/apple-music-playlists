"""Login gateway contract with a synthetic SDK; no upstream requests or credentials."""
import shutil
import json
import tempfile
import subprocess
import unittest
from pathlib import Path


class QrGatewayTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Optional Node gateway runtime unavailable")
    def test_managed_main_uses_ephemeral_port_and_exits_when_parent_pipe_closes(self):
        gateway = Path(__file__).resolve().parent.parent / "beta" / "qr_gateway.cjs"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sdk = root / "node_modules/@neteasecloudmusicapienhanced/api"
            sdk.mkdir(parents=True)
            (sdk / "index.js").write_text("module.exports = {};", encoding="utf-8")
            process = subprocess.Popen([shutil.which("node"), str(gateway), str(root), "0"],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8", cwd=root)
            try:
                # communicate closes the parent's pipe; no upstream route is invoked.
                stdout, stderr = process.communicate(input="", timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
                ready = json.loads(stdout)
                self.assertTrue(ready["ready"])
                self.assertTrue(ready["login_only"])
                self.assertGreaterEqual(ready["port"], 1024)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)

    @unittest.skipUnless(shutil.which("node"), "Optional Node gateway runtime unavailable")
    def test_loopback_login_only_no_origin_no_cache_and_sanitized_errors(self):
        gateway = Path(__file__).resolve().parent.parent / "beta" / "qr_gateway.cjs"
        script = r"""
const assert = require('node:assert/strict');
const http = require('node:http');
const {createGateway} = require(process.argv[1]);
const calls = [];
const sdk = {
 login_qr_key: async data => {calls.push(data); return {body:{code:200,data:{unikey:'synthetic'}}};},
 login_qr_create: async data => ({body:{code:200,data:{qrimg:'synthetic'}}}),
 login_qr_check: async data => ({body:{code:803,cookie:'MUSIC_U=synthetic'}}),
 user_account: async data => {throw {body:{cookie:'DO-NOT-EXPOSE'}};},
};
const server = createGateway(sdk);
function request(port,path,method='POST',data='',headers={}) {
 return new Promise((resolve,reject) => {
  const req=http.request({hostname:'127.0.0.1',port,path,method,headers:{'Content-Type':'application/x-www-form-urlencoded',...headers}}, res => {
   let raw=''; res.on('data',x=>raw+=x);res.on('end',()=>resolve({status:res.statusCode,body:JSON.parse(raw),headers:res.headers}));
  });req.on('error',reject);req.end(data);
 });
}
server.listen(0,'127.0.0.1',async()=>{
 try {
  const port=server.address().port;
  assert.equal(server.address().address,'127.0.0.1');
  let r=await request(port,'/health','GET');assert.equal(r.body.login_only,true);
  assert.equal(r.headers['cache-control'],'no-store');
  assert.equal(r.headers['access-control-allow-origin'],undefined);
  r=await request(port,'/login/qr/key','POST','type=3');assert.equal(r.body.data.unikey,'synthetic');
  assert.equal(calls.length,1);assert.equal(calls[0].timeout,10000);assert.equal(calls[0].randomCNIP,false);
  for(const [path,method,data,headers,status] of [
   ['/playlist/create','POST','',{},404],
   ['/login/qr/check?key=secret','POST','',{},404],
   ['/login/qr/key','GET','',{},404],
   ['/login/qr/key','POST','',{'Origin':'https://evil.example'},403],
   ['/login/qr/key','POST','',{'Host':'evil.example:'+port},403],
   ['/login/qr/key','POST','proxy=https://evil.example',{},400],
   ['/login/qr/key','POST','',{'Content-Type':'application/json'},415],
  ]) {r=await request(port,path,method,data,headers);assert.equal(r.status,status);}
  assert.equal(calls.length,1);
  r=await request(port,'/user/account','POST','cookie=MUSIC_U%3Dsynthetic');
  assert.equal(r.status,502);assert.equal(JSON.stringify(r).includes('DO-NOT-EXPOSE'),false);
  r=await request(port,'/login/qr/check','POST','key=synthetic');
  assert.equal(r.body.code,803);assert.equal(r.body.cookie,'MUSIC_U=synthetic');
  process.stdout.write('Gateway offline security contract passed.\n');
 }catch(e){process.stderr.write('Gateway offline contract failed.\n');process.exitCode=1;}
 finally{server.close();}
});
"""
        result = subprocess.run([shutil.which("node"), "-e", script, str(gateway)],
                                capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
