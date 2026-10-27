import { headers } from "next/headers";
import QRCode from "qrcode";
import { publicUrl } from "@/lib/lan.mjs";

/** The QR code for this portal's network address, built per request so it follows the laptop's IP. */
export async function QrCard() {
  const url = publicUrl((await headers()).get("host"));
  const svg = await QRCode.toString(url, { type: "svg", margin: 1, errorCorrectionLevel: "M", color: { dark: "#1c1819", light: "#ffffff" } });
  return (
    <figure className="qr">
      <div className="qr-code" role="img" aria-label={`QR code for ${url}`} dangerouslySetInnerHTML={{ __html: svg }} />
      <figcaption>
        <b>Scan to open on your phone</b>
        <a href={url} className="mono">{url}</a>
        <span>Same Wi-Fi as the presenter&apos;s laptop</span>
      </figcaption>
    </figure>
  );
}

export function QrSkeleton() {
  return <figure className="qr"><div className="qr-code qr-empty" /><figcaption><b>Scan to open on your phone</b></figcaption></figure>;
}
