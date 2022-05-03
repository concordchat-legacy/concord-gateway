# Blackbird
Blackbird is Reduxs fast Core WebSocket API, made for scalability

# Deploying in Production
In production we **really** recommend using a load balancer alongside a kubernetes cluster,
for example a websocket connection can max have on most languages about 10,000/15,000 connections 
per kubernetes node while still being "*stable*" (thinking this is a echo application),
Blackbird can only handle about 5,000 connections while being minimally stable.
