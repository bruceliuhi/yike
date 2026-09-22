import { useEffect, useRef, useState, type FormEvent } from "react";
import { CaretDown, CaretUp } from "@phosphor-icons/react";
import { useApp } from "../app/context";
import { useAction } from "../app/hooks";
import { boundedRequest, RequestCancelled } from "../app/boundedRequest";
import { errorMessage } from "../services/contracts";
import type { Session } from "../domain/models";
import { safeReturnTo } from "../domain/routes";
import { Button, Field, Modal, Notice } from "../components/ui";
import logo from "../assets/logo.png";

export function LoginPage() {
  const { service, session, route, navigate, refreshSession } = useApp();
  const returnTo = safeReturnTo(route.query.get("returnTo"), "/workbench");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [tokenOpen, setTokenOpen] = useState(false);
  const [token, setToken] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [cooldown, setCooldown] = useState(0);
  const [information, setInformation] = useState<string | null>(null);
  const login = useAction();
  const [smsBusy, setSmsBusy] = useState(false);
  const [smsError, setSmsError] = useState("");
  const smsGeneration = useRef(0);
  const smsController = useRef<AbortController | null>(null);
  const loginController = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      smsGeneration.current++;
      smsController.current?.abort();
      loginController.current?.abort();
    };
  }, []);
  // A real session refresh may remount the login page under its new user key.
  // Only an established server identity can continue after that remount.
  useEffect(() => {
    if (session.authenticated && session.userId?.trim()) navigate(returnTo);
  }, [navigate, returnTo, session.authenticated, session.userId]);
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((n) => n - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);
  const validPhone = () => {
    if (!/^1\d{10}$/.test(phone.trim())) {
      setErrors({ phone: "请输入 11 位手机号码。" });
      return false;
    }
    setErrors({});
    return true;
  };
  const requestCode = async () => {
    if (!validPhone() || cooldown > 0 || smsBusy) return;
    login.setError("");
    const request = ++smsGeneration.current;
    const abort = new AbortController();
    smsController.current?.abort();
    smsController.current = abort;
    const requestedPhone = phone.trim();
    setSmsBusy(true);
    setSmsError("");
    try {
      const result = await boundedRequest(() => service.requestCode(requestedPhone), {
        signal: abort.signal,
        timeoutMessage: "验证码请求超时，发送结果尚未确认。请稍后检查短信或重试。",
      });
      if (!mounted.current || request !== smsGeneration.current) return;
      if (!Number.isFinite(result.retryAfter) || result.retryAfter < 0)
        throw new Error("验证码服务响应无效，请稍后重试。");
      setCooldown(Math.max(1, Math.min(300, Math.ceil(result.retryAfter))));
    } catch (error) {
      if (mounted.current && request === smsGeneration.current && !(error instanceof RequestCancelled))
        setSmsError(errorMessage(error));
    } finally {
      if (mounted.current && request === smsGeneration.current) setSmsBusy(false);
    }
  };
  const performLogin = async (operation: () => Promise<Session>) => {
    await login.run(async () => {
      const abort = new AbortController();
      loginController.current = abort;
      const result = await boundedRequest(operation, {
        signal: abort.signal,
        timeoutMessage: "登录请求超时，结果尚未确认。请稍后重试并重新确认会话。",
      });
      if (!mounted.current) return;
      if (!result.authenticated)
        throw new Error("登录尚未完成，请核对凭证后重试。");
      const established = await boundedRequest(signal => refreshSession(signal), {
        signal: abort.signal,
        timeoutMessage: "会话确认超时，登录状态尚未核实。请稍后重试。",
      });
      if (!established.authenticated || !established.userId?.trim())
        throw new Error("登录会话尚未建立或已失效，请核对凭证后重试。");
      if (!mounted.current) return;
      setCode("");
      setToken("");
      navigate(returnTo);
    });
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!validPhone()) return;
    if (!/^\d{6}$/.test(code)) {
      setErrors({ code: "请输入 6 位短信验证码。" });
      return;
    }
    await performLogin(() =>
      service.login(phone.trim(), code),
    );
  };
  const submitToken = async (event: FormEvent) => {
    event.preventDefault();
    if (!token.trim()) {
      setErrors({ token: "请输入已有访问凭证。" });
      return;
    }
    setErrors({});
    await performLogin(() => service.loginToken(token.trim()));
  };
  return (
    <main className="login-layout">
      <section className="login-brand" aria-label="意客 AI">
        <div className="login-wordmark">
          <img src={logo} alt="" />
          <span>意客AI</span>
        </div>
        <h1>找到值得联系的新需求</h1>
        <p>找需求 · 看证据 · 跟进联系</p>
      </section>
      <section className="login-panel" aria-labelledby="login-title">
        <h2 id="login-title">欢迎使用意客AI</h2>
        <p className="page-description">登录后开启商机发现与跟进工作</p>
        <form onSubmit={submit} noValidate>
          <Field label="手机号码" required error={errors.phone}>
            <input
              aria-label="手机号码"
              type="tel"
              autoComplete="tel"
              inputMode="tel"
              maxLength={11}
              placeholder="请输入手机号码"
              value={phone}
              disabled={login.busy}
              onChange={(e) => {
                smsGeneration.current++;
                smsController.current?.abort();
                setSmsBusy(false);
                setCooldown(0);
                setCode("");
                setPhone(e.target.value);
                setErrors({});
                login.setError("");
                setSmsError("");
              }}
            />
          </Field>
          <Field label="短信验证码" required error={errors.code}>
            <div className="login-code-row">
              <input
                aria-label="短信验证码"
                type="password"
                autoComplete="one-time-code"
                inputMode="numeric"
                maxLength={6}
                placeholder="请输入验证码"
                value={code}
                disabled={login.busy}
                onChange={(e) => {
                  setCode(e.target.value);
                  setErrors({});
                  login.setError("");
                }}
              />
              <Button
                onClick={() => void requestCode()}
                loading={smsBusy}
                disabled={cooldown > 0 || login.busy}
              >
                {cooldown > 0 ? `${cooldown} 秒后重试` : "获取验证码"}
              </Button>
            </div>
          </Field>
          {smsError && <Notice tone="error">{smsError}</Notice>}
          <p>首次注册自动开通 3 天试用，无需试用码；重复登录不会重置试用期。</p>
          {!tokenOpen && login.error && (
            <Notice tone="error">{login.error}</Notice>
          )}
          <Button
            type="submit"
            variant="primary"
            className="login-submit"
            loading={login.busy}
          >
            登录
          </Button>
        </form>
        <div className="login-token">
          <Button
            variant="ghost"
            aria-expanded={tokenOpen}
            disabled={login.busy}
            onClick={() => {
              setTokenOpen(!tokenOpen);
              setToken("");
              setErrors({});
              login.setError("");
            }}
          >
            使用已有访问凭证 {tokenOpen ? <CaretUp /> : <CaretDown />}
          </Button>
          {tokenOpen && (
            <form onSubmit={submitToken} noValidate>
              <Field
                label="短期访问凭证"
                required
                error={errors.token}
                hint="使用已开通客户空间的短期凭证登录。"
              >
                <input
                  aria-label="短期访问凭证"
                  type="password"
                  autoComplete="off"
                  maxLength={8192}
                  value={token}
                  disabled={login.busy}
                  placeholder="粘贴已有访问凭证"
                  onChange={(e) => {
                    setToken(e.target.value);
                    setErrors({});
                  }}
                />
              </Field>
              {login.error && <Notice tone="error">{login.error}</Notice>}
              <Button type="submit" variant="primary" loading={login.busy}>
                使用凭证登录
              </Button>
            </form>
          )}
        </div>
        <footer className="login-footer">
          {["用户协议", "隐私政策", "联系支持"].map((title) => (
            <Button
              key={title}
              variant="ghost"
              onClick={() => setInformation(title)}
            >
              {title}
            </Button>
          ))}
        </footer>
      </section>
      {information && (
        <Modal
          title={information}
          onClose={() => setInformation(null)}
          footer={<Button onClick={() => setInformation(null)}>关闭</Button>}
        >
          <p>
            {information === "联系支持"
              ? "请联系为你开通客户空间的服务方。可在账号与授权中获取不包含凭证的诊断信息。"
              : "本构建尚未配置正式文件。请向服务方取得并阅读相应文件后使用客户服务。"}
          </p>
        </Modal>
      )}
    </main>
  );
}
