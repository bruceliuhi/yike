import {expect, it} from 'vitest';
import {connectionOperationSchema, parseConnectionReceipt} from '../src/shared/connectionOperation';
import {validatedConnectionOperation} from '../src/main/connectionServicePolicy';
import {validatedOperation} from '../src/main/servicePolicy';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const request = {request_id: id(1), action: 'VERIFY', device_id: id(2), connection_id: id(3), expected_connection_version: 1,
  platform: 'XIAOHONGSHU', account_public_id: '66c01234abcdef0123456789', session_ref: 'vault://platform/profile-1'};
const receipt = {request_id: id(1), action: 'VERIFY', device_id: id(2), state: 'SUCCEEDED', connection_id: id(3), connection_version: 2,
  connection_status: 'CONNECTED', error_code: null};
it('accepts strict owner verification and exact original receipt with state-change version', () => {
  expect(connectionOperationSchema.parse(request)).toEqual(request);
  expect(parseConnectionReceipt(receipt, request)).toEqual(receipt);
  expect(parseConnectionReceipt({...receipt, connection_version: 1}, request).connection_version).toBe(1);
});
it.each([{extra: true}, {expected_connection_version: true}, {connection_id: null}, {session_ref: 'cookie=secret'},
  {account_public_id: ' padded '}, {action: 'VERIFY', expected_connection_version: 0}, {device_id: '../path'}])('rejects unsafe request %#', change => {
  expect(connectionOperationSchema.safeParse({...request, ...change}).success).toBe(false);
});
it.each([{request_id: id(9)}, {action: 'REGISTER'}, {device_id: id(9)}, {connection_id: id(9)}, {connection_version: 3},
  {connection_status: 'UNVERIFIED'}, {error_code: 'secret'}, {extra: true}])('rejects unbound successful receipt %#', change => {
  expect(() => parseConnectionReceipt({...receipt, ...change}, request)).toThrow();
});
it('serializes private fixed routes and never adds them to public renderer policy', () => {
  expect(validatedConnectionOperation({operation: 'connections.apply', payload: request})).toEqual({path: '/api/ui/connection-operations', method: 'POST', body: JSON.stringify(request), logout: false});
  expect(validatedConnectionOperation({operation: 'connections.receipt', payload: {request_id: id(1)}})?.path).toBe(`/api/ui/connection-operations/${id(1)}`);
  expect(validatedConnectionOperation({operation: 'connections.current'})).toMatchObject({path: '/api/ui/connections', method: 'GET'});
  expect(validatedOperation({operation: 'connections.apply', payload: request})).toBeNull();
  expect(validatedConnectionOperation({operation: 'connections.receipt', payload: {request_id: '../secret'}})).toBeNull();
});
