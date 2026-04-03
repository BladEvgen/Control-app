function loadImageFromFile(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("image decode"));
    };
    img.src = url;
    img.decoding = "async";
  });
}

export async function fileForPadUpload(
  source: File,
  maxLongSide = 720,
  quality = 0.82,
): Promise<File> {
  if (!source.type.startsWith("image/")) return source;

  let releaseBitmap: (() => void) | undefined;

  try {
    const bitmap = await createImageBitmap(source);
    releaseBitmap = () => bitmap.close();
    const long = Math.max(bitmap.width, bitmap.height);
    const scale = long > maxLongSide ? maxLongSide / long : 1;
    const tw = Math.max(1, Math.round(bitmap.width * scale));
    const th = Math.max(1, Math.round(bitmap.height * scale));

    const canvas = document.createElement("canvas");
    canvas.width = tw;
    canvas.height = th;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) {
      releaseBitmap();
      return source;
    }
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bitmap, 0, 0, tw, th);
    releaseBitmap();
    releaseBitmap = undefined;

    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, "image/jpeg", quality);
    });
    if (!blob) return source;

    const base = source.name.replace(/\.[^.]+$/, "") || "frame";
    return new File([blob], `${base}-pad.jpg`, { type: "image/jpeg" });
  } catch {
    releaseBitmap?.();
  }

  try {
    const img = await loadImageFromFile(source);
    const iw = img.naturalWidth;
    const ih = img.naturalHeight;
    if (!iw || !ih) return source;

    const long = Math.max(iw, ih);
    const scale = long > maxLongSide ? maxLongSide / long : 1;
    const tw = Math.max(1, Math.round(iw * scale));
    const th = Math.max(1, Math.round(ih * scale));

    const canvas = document.createElement("canvas");
    canvas.width = tw;
    canvas.height = th;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return source;

    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, 0, 0, tw, th);

    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, "image/jpeg", quality);
    });
    if (!blob) return source;

    const base = source.name.replace(/\.[^.]+$/, "") || "frame";
    return new File([blob], `${base}-pad.jpg`, { type: "image/jpeg" });
  } catch {
    return source;
  }
}
