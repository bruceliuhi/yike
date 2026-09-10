import {expect, it, vi} from 'vitest';
import {createCipheriv, createDecipheriv, createPrivateKey, createPublicKey, randomBytes} from 'node:crypto';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createServiceClient} from '../../src/main/serviceClient';
import {createDeviceIdentityController} from '../../src/main/deviceIdentityController';
import {createPlatformConnectionController} from '../../src/main/platformConnectionController';
import {createConnectionProfileStore} from '../../src/main/connectionProfileStore';
import {createForegroundCollectionController} from '../../src/main/foregroundCollectionController';
import {createExecutionJournal} from '../../src/main/executionJournal';
import {createExecutionSession} from '../../src/main/executionSession';
import {createCandidateJournal} from '../../src/main/candidateJournal';
import {createCandidateSession} from '../../src/main/candidateSession';
import type {NativeLoginPlatform} from '../../src/shared/platformAccount';

const names = ['BASE', 'USER', 'TOKEN', 'SEED', 'START', 'ACCOUNTS', 'RECORDS'] as const;
const platforms: NativeLoginPlatform[] = ['XIAOHONGSHU', 'DOUYIN', 'BILIBILI'];

it.skipIf(!names.some(name => process.env[`YIKE_MULTIPLATFORM_LIVE_${name}`]))(
  'runs and recovers the original three-platform task over real HTTP and restricted PostgreSQL', async () => {
    const values = Object.fromEntries(names.map(name => [name, process.env[`YIKE_MULTIPLATFORM_LIVE_${name}`]]));
    expect(Object.values(values).every(Boolean)).toBe(true);
    expect(Object.keys(process.env).filter(name => /DATABASE|^POSTGRES_/i.test(name))).toEqual([]);
    expect(process.versions.node.split('.')[0]).toBe('24');
    const base = values.BASE!; expect(new URL(base).hostname).toBe('127.0.0.1');
    const template = JSON.parse(values.START!);
    const accounts = JSON.parse(values.ACCOUNTS!) as Record<NativeLoginPlatform, string>;
    const records = JSON.parse(values.RECORDS!) as Record<NativeLoginPlatform, unknown[]>;
    const privateKey = createPrivateKey({format: 'der', type: 'pkcs8', key: Buffer.concat([
      Buffer.from('302e020100300506032b657004220420', 'hex'), Buffer.from(values.SEED!, 'hex')])});
    const key = {scope: {serviceOrigin: base, userId: values.USER!, deviceId: template.device_id},
      privateKey: privateKey.export({format: 'pem', type: 'pkcs8'}).toString(),
      publicKey: createPublicKey(privateKey).export({format: 'jwk'}).x!};
    const secret = randomBytes(32);
    const protection = {isEncryptionAvailable: () => true,
      encryptString(value: string) {const nonce=randomBytes(12), cipher=createCipheriv('aes-256-gcm',secret,nonce);
        const body=Buffer.concat([cipher.update(value,'utf8'),cipher.final()]);return Buffer.concat([nonce,cipher.getAuthTag(),body]);},
      decryptString(value: Buffer) {const cipher=createDecipheriv('aes-256-gcm',secret,value.subarray(0,12));
        cipher.setAuthTag(value.subarray(12,28));return Buffer.concat([cipher.update(value.subarray(28)),cipher.final()]).toString('utf8');}};
    const directory = await mkdtemp(path.join(tmpdir(), 'yike-multiplatform-live-'));
    const store = createConnectionProfileStore({directory: path.join(directory, 'profiles'), protection});
    const executionJournal = () => createExecutionJournal({directory: path.join(directory, 'execution'), protection});
    const candidateJournal = () => createCandidateJournal({directory: path.join(directory, 'candidate'), protection});
    const journalScope = {serviceOrigin: base, userId: values.USER!};
    let cookie='', candidateWrites=0, loseSecond=true;
    const taskResponses: any[]=[]; const executionWrites:string[]=[]; const candidateReads:string[]=[];
    const client=createServiceClient({baseUrl:base,clearSession:async()=>{cookie='';},fetch:async(url,init)=>{
      const headers=new Headers(init.headers);if(cookie)headers.set('Cookie',cookie);
      const response=await fetch(url,{...init,headers});
      const session=response.headers.getSetCookie().find(value=>value.startsWith('pilot_session='));if(session)cookie=session.split(';',1)[0];
      expect(response.headers.get('cache-control')).toBe('no-store');
      if(init.method==='POST'&&url.endsWith('/execution-operations'))executionWrites.push(JSON.parse(String(init.body)).request.operation);
      if(init.method==='GET'&&new URL(url).pathname.startsWith('/api/ui/execution-tasks/'))taskResponses.push(structuredClone(await response.clone().json()));
      if(init.method==='GET'&&new URL(url).pathname.startsWith('/api/ui/candidate-batches/'))candidateReads.push(url);
      if(init.method==='POST'&&url.endsWith('/candidate-batches')){candidateWrites++;if(response.ok&&candidateWrites===2&&loseSecond){
        loseSecond=false;await response.json();throw new Error('controlled loss after second platform commit');}}
      return response;
    }});
    const identity=createDeviceIdentityController({service:client,identityFactory:()=>({prepare:async()=>
      ({state:'READY' as const,deviceId:template.device_id,credentialVersion:template.credential_version})})});
    const controllers:ReturnType<typeof createForegroundCollectionController>[]=[];
    const starts:NativeLoginPlatform[]=[];const budgets:number[]=[];const profiles=new Map<NativeLoginPlatform,string>();
    const boundAccounts:string[]=[];const profilePaths:string[]=[];const driverTargets:any[]=[];
    function controller(){const c=createForegroundCollectionController({serviceOrigin:base,identity,store,
      executionJournal:executionJournal(),candidateJournal:candidateJournal(),
      configuration:{pythonExecutable:'C:/controlled/python.exe',projectRoot:'C:/controlled/project',runtimePath:'C:/controlled/runtime',profileRoot:'C:/controlled/profiles',outputRoot:'C:/controlled/output'},
      probe:async()=>true,sessions:scope=>({execution:createExecutionSession({serviceOrigin:base,transport:scope.transport,journal:executionJournal(),vault:{read:async()=>key}}),
        candidates:createCandidateSession({serviceOrigin:base,transport:scope.transport,journal:candidateJournal(),vault:{read:async()=>key}})}),
      driverFactory:options=>({start(input){const platform=input.target.platform as NativeLoginPlatform;starts.push(platform);budgets.push(input.maxRecords);
        expect(options.binding.expectedAccountPublicId).toBeDefined();boundAccounts.push(options.binding.expectedAccountPublicId!);
        profilePaths.push(options.profilePath);driverTargets.push(structuredClone(input.target));
        return {completed:Promise.resolve(structuredClone(records[platform])),async stop(){}};}})});controllers.push(c);return c;}
    try {
      expect((await identity.requestApi({operation:'session.login',payload:{token:values.TOKEN}})).ok).toBe(true);
      expect(await identity.prepare()).toEqual({state:'READY',deviceId:template.device_id,credentialVersion:template.credential_version});
      const targets=[];
      for(const platform of platforms){
        const observed={account_public_id:accounts[platform],checked_at:new Date().toISOString().replace(/\.\d{3}Z$/,'Z')};
        const connection=createPlatformConnectionController({serviceOrigin:base,identity,store,login:{start:({profileId})=>{
          profiles.set(platform,profileId);return {opened:Promise.resolve(),completed:Promise.resolve(observed),async stop(){}};}}});
        const opened=await connection.execute({action:'OPEN',platform});expect(opened.state).toBe('OPENED');if(opened.state!=='OPENED')throw new Error();
        await vi.waitFor(async()=>expect(await connection.execute({action:'CHECK',platform,flowId:opened.flowId})).toMatchObject({state:'CONNECTED'}),{timeout:5000,interval:50});
        const record=await store.read({serviceOrigin:base,userId:values.USER!,deviceId:template.device_id,platform});expect(record?.state).toBe('RESOLVED');
        const verified=record!.verification!;targets.push({platform,access_mode:'PLATFORM_ACCOUNT',connection_id:verified.connection_id!,connection_version:verified.expected_connection_version+1});
        await connection.shutdown();
      }
      const command={action:'START',humanConfirmed:true,requestId:template.request_id,profileVersionId:template.profile_version_id,
        strategyVersionId:template.strategy_version_id,configurationSha256:template.configuration_sha256,targets};
      const first=controller();expect(await first.execute({action:'CAPABILITIES'})).toMatchObject({state:'AVAILABLE',bindings:[
        {platform:'XIAOHONGSHU'},{platform:'DOUYIN'},{platform:'BILIBILI'}]});
      const begun=await first.start(command);expect(begun.state).toBe('RECORDED');if(begun.state!=='RECORDED')throw new Error();
      const taskId=begun.receipt.task_id;
      await vi.waitFor(async()=>expect(await first.execute({action:'STATUS',taskId})).toMatchObject(
        {localState:'UPLOAD_UNKNOWN',serverStatus:'RUNNING',stopConfirmed:false}),{timeout:10000,interval:50});
      expect(starts).toEqual(['XIAOHONGSHU','DOUYIN']);expect(budgets).toEqual([4,3]);expect(candidateWrites).toBe(2);
      expect(boundAccounts).toEqual(starts.map(platform=>accounts[platform]));
      expect(profilePaths).toEqual(starts.map(platform=>path.win32.join('C:/controlled/profiles',profiles.get(platform)!)));
      expect(driverTargets).toEqual(targets.slice(0,2));
      await first.shutdown();const recovered=controller();
      expect(await recovered.execute({action:'RECOVER',taskId,humanConfirmed:true,retry:false})).toMatchObject({state:'STATUS',serverStatus:'RUNNING',stopConfirmed:false,recordsUsed:3});
      expect(starts).toEqual(['XIAOHONGSHU','DOUYIN']);expect(candidateReads).toHaveLength(2);
      const resumed=await recovered.resumeStart(template.request_id);expect(resumed).toEqual(begun);
      await vi.waitFor(async()=>expect(await recovered.execute({action:'STATUS',taskId})).toMatchObject(
        {localState:'COMPLETED',serverStatus:'SUCCEEDED',stopConfirmed:true,recordsUsed:4}),{timeout:10000,interval:50});
      expect(starts).toEqual(platforms);expect(budgets).toEqual([4,3,3]);expect(candidateWrites).toBe(3);
      expect(boundAccounts).toEqual(platforms.map(platform=>accounts[platform]));
      expect(profilePaths).toEqual(platforms.map(platform=>path.win32.join('C:/controlled/profiles',profiles.get(platform)!)));
      expect(driverTargets).toEqual(targets);
      expect(executionWrites.filter(value=>value==='START')).toHaveLength(1);
      expect(taskResponses.some(task=>task.status==='RUNNING'&&task.stop_confirmed===false)).toBe(true);
      expect(taskResponses.every(task=>task.platform_runs.map((run:any)=>run.platform).join(',')==='XIAOHONGSHU,DOUYIN,BILIBILI')).toBe(true);
      expect((await executionJournal().list(journalScope)).filter(op=>op.operation==='START')).toHaveLength(1);
    } finally {
      for(const c of controllers)await c.shutdown();
      const cleanup=path.resolve(directory);if(path.dirname(cleanup)!==path.resolve(tmpdir())||!path.basename(cleanup).startsWith('yike-multiplatform-live-'))throw new Error('unsafe cleanup');
      await rm(cleanup,{recursive:true,force:true});
    }
  },45_000);
