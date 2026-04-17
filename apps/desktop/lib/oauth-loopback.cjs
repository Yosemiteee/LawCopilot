const http = require("http");

function readCallback(urlString) {
  const url = new URL(String(urlString || "").trim());
  return {
    hostname: url.hostname || "127.0.0.1",
    port: Number(url.port || 80),
    pathname: url.pathname || "/",
  };
}

function waitForLoopbackCallback(redirectUri, options = {}) {
  const callback = readCallback(redirectUri);
  const timeoutMs = Math.max(15_000, Number(options.timeoutMs || 180_000));
  const successMessage =
    String(options.successMessage || "").trim()
    || "Bağlantı tamamlandı. LawCopilot uygulamasına dönebilirsiniz.";
  const errorMessage =
    String(options.errorMessage || "").trim()
    || "Bağlantı tamamlanamadı. LawCopilot uygulamasına dönüp tekrar deneyin.";

  let cancel = () => {};

  const promise = new Promise((resolve, reject) => {
    let settled = false;
    let timeoutId = null;

    function cleanup(server) {
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
      try {
        server.close();
      } catch {
        return;
      }
    }

    const server = http.createServer((req, res) => {
      const requestUrl = new URL(req.url || "/", redirectUri);
      if (requestUrl.pathname !== callback.pathname) {
        res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("Bulunamadı.");
        return;
      }
      const body = requestUrl.searchParams.get("error") ? errorMessage : successMessage;
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(`<!doctype html><html lang="tr"><body style="font-family: sans-serif; padding: 24px;"><p>${body}</p></body></html>`);
      if (settled) {
        return;
      }
      settled = true;
      cleanup(server);
      resolve(requestUrl.toString());
    });

    server.on("error", (error) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup(server);
      if (error && (error.code === "EADDRINUSE" || error.code === "EACCES")) {
        reject(new Error("Yerel OAuth yönlendirme portu açılamadı. Tarayıcı girişini bitirdikten sonra yönlendirme adresini uygulamaya manuel yapıştırın."));
        return;
      }
      reject(error);
    });

    server.listen(callback.port, callback.hostname, () => {
      timeoutId = setTimeout(() => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup(server);
        reject(new Error("Yerel OAuth yönlendirme süresi doldu."));
      }, timeoutMs);
    });

    cancel = (reason = "Yerel OAuth yönlendirmesi iptal edildi.") => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup(server);
      reject(new Error(String(reason || "Yerel OAuth yönlendirmesi iptal edildi.")));
    };
  });

  promise.cancel = (reason) => cancel(reason);
  return promise;
}

module.exports = {
  readCallback,
  waitForLoopbackCallback,
};
