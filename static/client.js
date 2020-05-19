/* eslint-disable no-plusplus */
/* eslint-disable no-console */
function sysInfoListener() {
  const protocol = (window.location.protocol === 'https:') ? 'wss:' : 'ws:';
  const url = `${protocol}//${window.location.host}/sysinfo`;
  console.log(`Connecting to ${url}`);
  const sysInfoWS = new WebSocket(url);

  sysInfoWS.addEventListener('open', () => {
    console.log('sysInfoWS.onopen: Connected to the server');
  });

  sysInfoWS.addEventListener('message', (event) => {
    // console.log(`sysInfoWS.onmessage: Got message: ${event.data}`);
    const outputElement = document.getElementById('output');
    const message = JSON.parse(event.data);

    let cpuStats = '';
    let procStats = '';
    for (let i = 0; i < Object.keys(message).length; i++) {
      cpuStats += `CPU${i.toString().padEnd(3)} %${message[i].cpu_percent.toString().padEnd(6)} MEM %${message[i].memory_percent.toString().padEnd(6)} `;
      for (let j = 0; j < Object.keys(message[i].procs).length; j++) {
        cpuStats += `${message[i].procs[j].name.substr(0, 8).padEnd(8)}[${message[i].procs[j].pid}]-${message[i].procs[j].num_threads.toString().padEnd(6)} `;
        procStats += `${message[i].procs[j].name.substr(0, 8).padEnd(8)} ${message[i].procs[j].pid} `;
        procStats += `CPU${i.toString().padEnd(3)} %${message[i].procs[j].cpu_percent.toString().padEnd(6)} `;
        procStats += `MEM %${message[i].procs[j].memory_percent.toString().padEnd(6)} `;
        procStats += `Nthreads ${message[i].procs[j].num_threads.toString().padEnd(6)}\n`;
      }
      cpuStats += '\n';
    }
    cpuStats += '\n';
    outputElement.innerText = cpuStats + procStats;
  });
}

window.onload = sysInfoListener();
