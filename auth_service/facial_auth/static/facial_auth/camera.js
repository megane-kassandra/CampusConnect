(() => {
  const video = document.getElementById("camera");
  const canvas = document.getElementById("frame");
  const statusBox = document.getElementById("status");
  const startButton = document.getElementById("start");
  const stopButton = document.getElementById("stop");
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const recognitionUrl = document.body.dataset.recognitionUrl;
  let stream = null;
  let timer = null;
  let busy = false;

  function status(message) {
    statusBox.textContent = message;
  }

  function capture() {
    if (!video.videoWidth || !video.videoHeight) return Promise.resolve(null);
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.82));
  }

  async function identify() {
    if (busy || !stream) return;
    busy = true;
    try {
      const frame = await capture();
      if (!frame) return;
      const data = new FormData();
      data.append("frame", frame, "camera.jpg");
      const response = await fetch(recognitionUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        body: data,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Échec de la reconnaissance.");
      if (result.status === "no_face") status("Aucun visage détecté. Place ton visage dans le cadre.");
      else if (result.status === "multiple_faces") status("Plusieurs visages détectés. Une seule personne doit être devant la caméra.");
      else if (result.status === "unknown") status("Visage détecté, mais aucun compte correspondant.");
      else if (result.status === "recognized") {
        status(`Visage reconnu — compte ${result.user_id}, similarité ${result.similarity} %`);
      }
    } catch (error) {
      status(error.message);
    } finally {
      busy = false;
    }
  }

  startButton.addEventListener("click", async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      });
      video.srcObject = stream;
      startButton.disabled = true;
      stopButton.disabled = false;
      status("Caméra active. Recherche d'un visage…");
      timer = window.setInterval(identify, 1800);
      identify();
    } catch {
      status("Impossible d'ouvrir la caméra. Autorise son accès dans le navigateur.");
    }
  });

  stopButton.addEventListener("click", () => {
    window.clearInterval(timer);
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
    startButton.disabled = false;
    stopButton.disabled = true;
    status("Caméra arrêtée.");
  });
})();
