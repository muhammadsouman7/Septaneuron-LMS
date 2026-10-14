(function(){
  const canvas = document.getElementById('threadCanvas');
  const gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: true, antialias: false });

  if(!gl){
    canvas.style.display = 'none';
    document.querySelector('.hero').style.background = 'linear-gradient(135deg, #05080a, #041018)';
    return;
  }

  const vertexSrc = `#version 300 es
  in vec2 position;
  void main(){ gl_Position = vec4(position, 0.0, 1.0); }
  `;

  const fragmentSrc = `#version 300 es
  precision highp float;
  uniform vec2 iResolution;
  uniform float iTime;
  uniform float uSpeed;
  uniform float uThreadCount;
  uniform float uFrequency;
  uniform float uSpread;
  uniform float uTaper;
  uniform float uPosition;
  uniform float uFanMode;
  uniform float uGlow;
  uniform float uFalloff;
  uniform float uThickness;
  uniform float uBrightness;
  uniform float uOpacity;
  uniform float uMirror;
  uniform float uShimmer;
  uniform float uGrain;
  uniform float uGrainIntensity;
  uniform vec3 uColor1;
  uniform vec3 uColor2;
  uniform vec3 uColor3;
  uniform vec2 uMouse;
  uniform float uMouseStrength;
  uniform float uEnableMouse;
  uniform float uMouseActive;
  out vec4 fragColor;

  #define TAU 6.28318530718
  #define MAX_THREADS 10

  float glowFn(float x, float str, float dist){
    return dist / pow(max(x, 1e-4), str);
  }

  void main(){
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    float n = max(uThreadCount, 1.0);

    float pinchX = uFanMode < 0.5 ? 0.5 : (uFanMode < 1.5 ? 0.0 : 1.0);
    if (uEnableMouse > 0.5) {
      pinchX = mix(pinchX, uMouse.x, clamp(uMouseStrength, 0.0, 1.0) * uMouseActive);
    }

    float spreadDx = uSpread * abs(uv.x - pinchX);
    float baseT = iTime * uSpeed;
    float tauOverN = TAU / n;
    float mirror = uMirror > 0.5 ? sign(pinchX - uv.x) : 1.0;
    bool doShimmer = uShimmer > 0.5;
    float shimmerT = iTime * 1.7;
    float invThickness = 1.0 / max(uThickness, 0.01);
    float xFreq = uv.x * uFrequency;
    float yOff = uv.y - uPosition;
    float ciScale = n > 1.0 ? 1.0 / (n - 1.0) : 0.0;

    vec3 col = vec3(0.0);
    float gsum = 0.0;

    for (int idx = 0; idx < MAX_THREADS; idx++) {
      float i = float(idx);
      if (i >= n) break;

      float amplitude = spreadDx * (1.0 + i * uTaper);
      float shimmerV = doShimmer ? sin(shimmerT + i * 1.3) * 0.35 : 0.0;
      float phase = (baseT + i * tauOverN) * mirror + shimmerV;

      float sdf = abs(yOff + sin(xFreq + phase) * amplitude) * invThickness;

      float g = glowFn(sdf, uFalloff, uGlow);
      float ci = i * ciScale;
      vec3 threadCol = mix(uColor1, uColor2, ci);

      col += g * threadCol;
      gsum += g;
    }

    float coreAmt = smoothstep(0.5, 2.2, gsum);
    col = mix(col, uColor3 * gsum, coreAmt * 0.5);

    float bright = uBrightness;
    if (uEnableMouse > 0.5) {
      vec2 md = uv - uMouse;
      float d2 = dot(md, md);
      bright += clamp(uMouseStrength, 0.0, 1.0) * uMouseActive * exp(-d2 * 6.0) * 0.6;
    }
    col *= bright;

    float alpha = clamp(gsum, 0.0, 1.0) * uOpacity;
    vec3 outRgb = col * alpha;

    if (uGrain > 0.5) {
      float gv = (fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233)) + iTime) * 43758.5453) - 0.5) * uGrainIntensity;
      outRgb = clamp(outRgb + gv, 0.0, 1.0);
      alpha = clamp(alpha + gv, 0.0, 1.0);
    }

    fragColor = vec4(outRgb, alpha);
  }
  `;

  function compile(type, src){
    const shader = gl.createShader(type);
    gl.shaderSource(shader, src);
    gl.compileShader(shader);
    if(!gl.getShaderParameter(shader, gl.COMPILE_STATUS)){
      console.error(gl.getShaderInfoLog(shader));
    }
    return shader;
  }

  const vs = compile(gl.VERTEX_SHADER, vertexSrc);
  const fs = compile(gl.FRAGMENT_SHADER, fragmentSrc);
  const program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  gl.useProgram(program);

  const positions = new Float32Array([-1,-1, 3,-1, -1,3]);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
  const posLoc = gl.getAttribLocation(program, 'position');
  gl.enableVertexAttribArray(posLoc);
  gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

  function hexToRgb(hex){
    const r = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if(!r) return [1,1,1];
    return [parseInt(r[1],16)/255, parseInt(r[2],16)/255, parseInt(r[3],16)/255];
  }

  const U = {};
  ['iResolution','iTime','uSpeed','uThreadCount','uFrequency','uSpread','uTaper','uPosition',
   'uFanMode','uGlow','uFalloff','uThickness','uBrightness','uOpacity','uMirror','uShimmer',
   'uGrain','uGrainIntensity','uColor1','uColor2','uColor3','uMouse','uMouseStrength',
   'uEnableMouse','uMouseActive'].forEach(name => { U[name] = gl.getUniformLocation(program, name); });

  const settings = {
    color1: hexToRgb('#00BCD4'),
    color2: hexToRgb('#00BCD4'),
    color3: hexToRgb('#000080'),
    speed: 0.2,
    threadCount: 7,
    frequency: 6,
    spread: 0.22,
    taper: 1.0,
    position: 0.5,
    fanMode: 1, // left
    glow: 0.025,
    falloff: 0.6,
    thickness: 1.1,
    brightness: 0.6,
    opacity: 1.0,
    mirror: 1.0,
    shimmer: 0.0,
    grain: 1.0,
    grainIntensity: 0.03,
    mouseInteraction: 1.0,
    mouseStrength: 0.2
  };

  gl.uniform3fv(U.uColor1, settings.color1);
  gl.uniform3fv(U.uColor2, settings.color2);
  gl.uniform3fv(U.uColor3, settings.color3);
  gl.uniform1f(U.uSpeed, settings.speed);
  gl.uniform1f(U.uThreadCount, settings.threadCount);
  gl.uniform1f(U.uFrequency, settings.frequency);
  gl.uniform1f(U.uSpread, settings.spread);
  gl.uniform1f(U.uTaper, settings.taper);
  gl.uniform1f(U.uPosition, settings.position);
  gl.uniform1f(U.uFanMode, settings.fanMode);
  gl.uniform1f(U.uGlow, settings.glow);
  gl.uniform1f(U.uFalloff, settings.falloff);
  gl.uniform1f(U.uThickness, settings.thickness);
  gl.uniform1f(U.uBrightness, settings.brightness);
  gl.uniform1f(U.uOpacity, settings.opacity);
  gl.uniform1f(U.uMirror, settings.mirror);
  gl.uniform1f(U.uShimmer, settings.shimmer);
  gl.uniform1f(U.uGrain, settings.grain);
  gl.uniform1f(U.uGrainIntensity, settings.grainIntensity);
  gl.uniform1f(U.uEnableMouse, settings.mouseInteraction);
  gl.uniform1f(U.uMouseStrength, settings.mouseStrength);

  const currentMouse = [0.5, 0.5];
  const targetMouse = [0.5, 0.5];
  let currentActive = 0;
  let targetActive = 0;

  function resize(){
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.floor(rect.width * dpr));
    const h = Math.max(1, Math.floor(rect.height * dpr));
    if(canvas.width !== w || canvas.height !== h){
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
      gl.uniform2f(U.iResolution, w, h);
    }
  }
  window.addEventListener('resize', resize);
  resize();

  const heroEl = document.querySelector('.hero');
  heroEl.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    targetMouse[0] = (e.clientX - rect.left) / rect.width;
    targetMouse[1] = 1.0 - (e.clientY - rect.top) / rect.height;
    targetActive = 1;
  });
  heroEl.addEventListener('mouseleave', () => { targetActive = 0; });

  const t0 = performance.now();
  function loop(t){
    resize();
    const time = (t - t0) * 0.001;
    currentMouse[0] += 0.05 * (targetMouse[0] - currentMouse[0]);
    currentMouse[1] += 0.05 * (targetMouse[1] - currentMouse[1]);
    currentActive += 0.05 * (targetActive - currentActive);

    gl.uniform1f(U.iTime, time);
    gl.uniform2f(U.uMouse, currentMouse[0], currentMouse[1]);
    gl.uniform1f(U.uMouseActive, currentActive);

    gl.clearColor(0,0,0,0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();

