# Origins License Server

Origins Bot için online lisans API'si.

## Render kurulumu

1. Bu klasördeki `main.py`, `requirements.txt` ve `render.yaml` dosyalarını GitHub deponuzun KÖK dizinine yükleyin.
2. Render Dashboard > New > Blueprint seçin.
3. GitHub deponuzu bağlayın.
4. Render `render.yaml` dosyasını okuyacaktır.
5. `ADMIN_KEY` istendiğinde uzun ve rastgele bir parola girin. Bunu GitHub'a yazmayın.
6. Deploy Blueprint deyin.
7. Kurulum tamamlandığında servis adresiniz örneğin:
   `https://origins-license-api.onrender.com`
   biçiminde olur.

## Test

Tarayıcıda servis adresinizi açtığınızda:
`{"ok":true,"service":"Origins License Server"}`

görmelisiniz.

API belgeleri:
`SERVIS_ADRESI/docs`

## Güvenlik

- `ADMIN_KEY` kesinlikle GitHub'a yüklenmemelidir.
- Müşteri uygulamasına `ADMIN_KEY` konulmamalıdır.
- Müşteri uygulaması yalnızca `/verify` endpoint'ini kullanacaktır.
- Yönetim endpoint'leri `X-Admin-Key` header'ı ister.
