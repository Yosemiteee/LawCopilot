export function normalizeUiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    const message = String(error.message || '').trim();
    if (!message) return fallback;
    if (/failed to fetch/i.test(message) || /networkerror/i.test(message)) {
      return 'Yerel servisle bağlantı koptu. Uygulamayı kapatıp yeniden açın; sorun sürerse Ayarlar veya Çekirdek ekranından durumu yenileyin.';
    }
    if (/backend_unreachable/i.test(message)) {
      return 'Yerel servis şu an erişilemiyor. Uygulamayı yeniden açın.';
    }
    return message;
  }
  return fallback;
}
