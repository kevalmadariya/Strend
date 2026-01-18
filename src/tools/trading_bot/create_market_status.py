from ..base import DynamicTool
from ..base import ToolParam

def makeTool(router):
    """
    Factory function for the Forecast Creation Tool.
    """
    def func(unique_id):
        # 'id' is the unique context ID passed during agent initialization
        
        # 1. Define the actual logic the LLM will execute
        async def create_forecast(region: str):
            """
            The actual function logic that runs when the agent calls this tool.
            """
            print(f"✅ Executing Forecast Logic for ID: {unique_id} in Region: {region}")
            # Perform actual DB logic here...
            return f"Market status created for {region} (Context: {unique_id})"

        # 2. Return the Tool Definition (Dedent this block!)
        return DynamicTool(
            name="check_market_status",
            description="Create market status",
            triggers="Create market status for a region",
            function=create_forecast, # Pass the function defined above
            parameters=[
                ToolParam(
                    name="region", 
                    type="string", 
                    description="Region Asia, Europe, America etc.", 
                    enums=["Asia", "Europe", "America"], 
                    required=True
                )
            ],
            endpoint="/create-forecast-order",
            router=router
        )

    return func