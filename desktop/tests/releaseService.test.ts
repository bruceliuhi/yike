import {expect,it} from 'vitest';
import {releaseServiceBuildInput} from '../build/releaseService';
import {clientServiceConfiguration} from '../src/main/clientServiceConfiguration';

it('requires a configured HTTPS origin for release packaging',()=>{
 expect(()=>releaseServiceBuildInput({},true)).toThrow('RELEASE_SERVICE_URL_REQUIRED');
 expect(releaseServiceBuildInput({},false)).toBeNull();
 expect(releaseServiceBuildInput({YIKE_RELEASE_SERVICE_URL:'https://PILOT.example:443/'},true)).toBe('https://pilot.example');
 for(const url of ['http://127.0.0.1:8787','https://u:secret@pilot.example','https://pilot.example/path','https://pilot.example/?token=secret',' https://pilot.example'])
  expect(()=>releaseServiceBuildInput({YIKE_RELEASE_SERVICE_URL:url},true)).toThrow('RELEASE_SERVICE_URL_INVALID');
});
it('uses bundled origin for installed clients and never accepts a runtime redirect',()=>{
 const env={YIKE_SERVICE_URL:'https://other.example',YIKE_ALLOW_LOOPBACK_HTTP:'1'};
 expect(clientServiceConfiguration({packaged:true,bundled:'https://pilot.example',env})).toBe('https://pilot.example');
 expect(clientServiceConfiguration({packaged:true,bundled:null,env})).toBeNull();
 expect(clientServiceConfiguration({packaged:true,bundled:'http://127.0.0.1',env})).toBeNull();
});
it('retains explicitly configured development service without embedding secrets',()=>{
 expect(clientServiceConfiguration({packaged:false,bundled:null,env:{YIKE_SERVICE_URL:'http://127.0.0.1:8787'}})).toBeNull();
 expect(clientServiceConfiguration({packaged:false,bundled:null,env:{YIKE_SERVICE_URL:'http://127.0.0.1:8787',YIKE_ALLOW_LOOPBACK_HTTP:'1'}})).toBe('http://127.0.0.1:8787');
});
