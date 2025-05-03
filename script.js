mapboxgl.accessToken =
  "pk.eyJ1Ijoic3ViaGFtcHJlZXQiLCJhIjoiY2toY2IwejF1MDdodzJxbWRuZHAweDV6aiJ9.Ys8MP5kVTk5P9V2TDvnuDg";

// Add error logging
function setupMap(center) {
  const map = new mapboxgl.Map({
    container: "map",
    style: "mapbox://styles/mapbox/streets-v11",
    center: center,
    zoom: 15,
  });

  const nav = new mapboxgl.NavigationControl();
  map.addControl(nav);

  const directions = new MapboxDirections({
    accessToken: mapboxgl.accessToken,
    profile: "mapbox/driving",
    alternatives: true,
    congestion: true,
    unit: "metric",
  });

  map.addControl(directions, "top-left");

  // Add a button to trigger vehicle count analysis
  const analyzeButton = document.createElement("button");
  analyzeButton.textContent = "Analyze Traffic";
  analyzeButton.className = "analyze-button";
  analyzeButton.style.position = "absolute";
  analyzeButton.style.bottom = "20px";
  analyzeButton.style.left = "20px";
  analyzeButton.style.padding = "10px 20px";
  analyzeButton.style.backgroundColor = "#4264fb";
  analyzeButton.style.color = "white";
  analyzeButton.style.border = "none";
  analyzeButton.style.borderRadius = "4px";
  analyzeButton.style.cursor = "pointer";
  analyzeButton.style.zIndex = "1";
  analyzeButton.style.display = "none"; // Hide initially until route is available

  document.getElementById("map").appendChild(analyzeButton);

  // Create a container for notifications
  const notificationContainer = document.createElement("div");
  notificationContainer.style.position = "absolute";
  notificationContainer.style.top = "20px";
  notificationContainer.style.right = "20px";
  notificationContainer.style.width = "300px";
  notificationContainer.style.zIndex = "2";
  document.getElementById("map").appendChild(notificationContainer);

  // Function to show a notification
  function showNotification(message, isWarning = false) {
    const notification = document.createElement("div");
    notification.innerHTML = message;
    notification.style.backgroundColor = isWarning
      ? "rgba(255,87,34,0.9)"
      : "rgba(33,150,243,0.9)";
    notification.style.color = "white";
    notification.style.padding = "15px";
    notification.style.marginBottom = "10px";
    notification.style.borderRadius = "4px";
    notification.style.boxShadow = "0 2px 5px rgba(0,0,0,0.2)";
    notification.style.transition = "opacity 0.5s";

    notificationContainer.appendChild(notification);

    // Remove after a few seconds
    setTimeout(() => {
      notification.style.opacity = "0";
      setTimeout(() => {
        notification.remove();
      }, 500);
    }, 7000);

    return notification;
  }

  // Add the reroute button but keep it hidden initially
  const rerouteButton = document.createElement("button");
  rerouteButton.textContent = "Use Alternative Route";
  rerouteButton.style.position = "absolute";
  rerouteButton.style.bottom = "20px";
  rerouteButton.style.left = "160px";
  rerouteButton.style.padding = "10px 20px";
  rerouteButton.style.backgroundColor = "#ff5722";
  rerouteButton.style.color = "white";
  rerouteButton.style.border = "none";
  rerouteButton.style.borderRadius = "4px";
  rerouteButton.style.cursor = "pointer";
  rerouteButton.style.zIndex = "1";
  rerouteButton.style.display = "none";
  document.getElementById("map").appendChild(rerouteButton);

  // Listen for the 'route' event which fires when a route is found
  directions.on("route", function (event) {
    console.log("Route event triggered:", event);

    if (!event.route || event.route.length === 0) {
      console.error("No route data available");
      analyzeButton.style.display = "none";
      rerouteButton.style.display = "none";
      showNotification(
        "Unable to calculate a route between these locations. Please try locations that are closer together.",
        true
      );
      return;
    }

    // Show the analyze button when a route is available
    analyzeButton.style.display = "block";
    rerouteButton.style.display = "none"; // Hide reroute button until we analyze

    // Store the current route information
    const sourceCoordinates = directions.getOrigin().geometry.coordinates;
    const destinationCoordinates =
      directions.getDestination().geometry.coordinates;

    analyzeButton.onclick = function () {
      // Create status indicator
      const statusNotification = showNotification("Analyzing traffic...");

      // Prepare route data
      const routeData = {
        source: sourceCoordinates,
        destination: destinationCoordinates,
      };

      // Send to backend
      fetch("http://127.0.0.1:5000/get_vehicle_count", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(routeData),
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Server responded with status: ${response.status}`);
          }
          return response.json();
        })
        .then((data) => {
          console.log("Success:", data);

          // Update status notification
          statusNotification.remove();

          if (data.needs_reroute) {
            // Show high traffic warning
            showNotification(
              `<strong>HIGH TRAFFIC ALERT!</strong><br>Vehicle count: ${data.vehicle_count}<br>An alternative route is available with estimated ${data.alternative_route.estimated_vehicle_count} vehicles.`,
              true
            );

            // Show reroute button
            rerouteButton.style.display = "block";

            // Store alternative route data
            rerouteButton.alternativeRoute = data.alternative_route;
          } else {
            showNotification(
              `Traffic analysis complete!<br>Vehicle count: ${data.vehicle_count}<br>Traffic is within normal limits.`
            );
          }
        })
        .catch((error) => {
          console.error("Error:", error);
          statusNotification.remove();
          showNotification("Error analyzing traffic: " + error.message, true);
        });
    };

    // Set up the reroute button to apply the alternative route
    rerouteButton.onclick = function () {
      if (rerouteButton.alternativeRoute) {
        const route = rerouteButton.alternativeRoute;

        // Clear current route
        directions.removeRoutes();

        // Add waypoints from alternative route
        const waypoints = route.waypoints.map((wp) => {
          return {
            coordinates: wp,
          };
        });

        // Set origin, destination and waypoints
        directions.setOrigin(route.source);
        directions.setDestination(route.destination);

        // Add each waypoint
        waypoints.forEach((wp) => {
          directions.addWaypoint(0, wp.coordinates);
        });

        showNotification(
          "Alternative route applied! This route should have less traffic."
        );

        // Hide reroute button after using it
        rerouteButton.style.display = "none";
      }
    };
  });
}

function successLocation(position) {
  setupMap([position.coords.longitude, position.coords.latitude]);
}

function errorLocation() {
  setupMap([-2.24, 53.48]);
}

navigator.geolocation.getCurrentPosition(successLocation, errorLocation, {
  enableHighAccuracy: true,
});
function sendToBackend(routeData) {
  console.log("Sending to backend:", routeData);
  // Comment this out temporarily for testing
  /*
  fetch('YOUR_BACKEND_API_URL/route', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(routeData)
  })
  .then(response => response.json())
  .then(data => {
    console.log('Success:', data);
  })
  .catch((error) => {
    console.error('Error:', error);
  });
  */
}

navigator.geolocation.getCurrentPosition(successLocation, errorLocation, {
  enableHighAccuracy: true,
});

function successLocation(position) {
  console.log("Got location:", position.coords);
  setupMap([position.coords.longitude, position.coords.latitude]);
}

function errorLocation(error) {
  console.error("Error getting location:", error);
  setupMap([-2.24, 53.48]);
}
