import { NextResponse } from "next/server";
import axios from "axios";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { endpoint, ...payload } = body;

    if (!endpoint) {
      return NextResponse.json(
        { error: "API Endpoint is required" },
        { status: 400 }
      );
    }

    // Forward the request to the Lambda
    const response = await axios.post(endpoint, payload, {
      headers: {
        "Content-Type": "application/json",
      },
    });

    return NextResponse.json(response.data);
  } catch (error: any) {
    console.error("Proxy error:", error.message);
    return NextResponse.json(
      { 
        error: error.message || "Internal Server Error",
        details: error.response?.data 
      },
      { status: error.response?.status || 500 }
    );
  }
}

