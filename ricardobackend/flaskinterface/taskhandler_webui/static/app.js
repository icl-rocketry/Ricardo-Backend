var url = 'http://' + location.host + '/telemetry'

console.log(location.host)
// var url = 'http://localhost:1337/telemetry'
var socket = io(url);
var telemetry_timeseries = [{}];
var prev_telemetry = {};
var rocket_route = [[]];

socket.on('connect', function(msg) { // (1)
    console.log('connected to websocket on ' + url)
});



socket.on('runningTasks', function (msg) { // (3)
    console.logo(msg)
});

socket.emit('getRunningTasks', {}, '/data_request_handler')
console.log("hi")