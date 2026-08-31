from network_as_code import NetworkAsCodeApi

# We initialize the client object with your application key
client = NetworkAsCodeApi(
    rapidapi_host="network-as-code.nokia.rapidapi.com",
    api_key="<your-application-key-here>",
)

# Retrieve the location of a device by providing its phone number
# and the maximum age of the location information in seconds
location = client.location.retrieve(
    device={"phone_number": "+999991234567"},
    max_age=3600,
)

# The location object contains fields for longitude, latitude and radius
print(location)