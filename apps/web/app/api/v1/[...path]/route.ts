import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { generateInternalApiToken } from "@/lib/identity-token";

async function proxyRequest(request: NextRequest, { path }: { path: string[] }) {
  const session = await auth();

  let user = session?.user?.email
    ? {
        id: session.user.id || "authjs-user",
        email: session.user.email,
        name: session.user.name || "",
      }
    : null;

  const targetPath = (path || []).join("/");
  const isPublicEndpoint =
    targetPath.startsWith("users/register") ||
    targetPath.startsWith("users/verify-credentials");

  if (!user && !isPublicEndpoint) {
    return NextResponse.json(
      {
        success: false,
        error: { code: "UNAUTHORIZED", message: "Authentication required. Please sign in." },
      },
      { status: 401 }
    );
  }

  const djangoUrl = process.env.DJANGO_API_URL || "http://127.0.0.1:8000";
  const queryString = request.nextUrl.search;
  // Ensure trailing slash for Django REST Framework routing conventions
  const formattedPath = targetPath.endsWith("/") ? targetPath : `${targetPath}/`;
  const targetUrl = `${djangoUrl}/api/v1/${formattedPath}${queryString}`;

  const headers = new Headers();
  if (user) {
    const token = generateInternalApiToken(user);
    headers.set("Authorization", `Bearer ${token}`);
  }
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }
  const accept = request.headers.get("accept");
  if (accept) {
    headers.set("Accept", accept);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
  };

  if (["POST", "PUT", "PATCH"].includes(request.method)) {
    if (contentType && contentType.includes("multipart/form-data")) {
      init.body = await request.arrayBuffer();
    } else {
      init.body = await request.text();
    }
  }

  try {
    const response = await fetch(targetUrl, init);

    // Support streaming SSE responses (e.g. for /api/v1/chat/stream/)
    if (response.headers.get("content-type")?.includes("text/event-stream")) {
      return new Response(response.body, {
        status: response.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        },
      });
    }

    // 204 No Content responses must have null body in Web Fetch API
    if (response.status === 204) {
      return new Response(null, {
        status: 204,
      });
    }

    const responseData = await response.text();
    return new Response(responseData, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/json",
      },
    });
  } catch (error: any) {
    return NextResponse.json(
      {
        success: false,
        error: {
          code: "BACKEND_UNAVAILABLE",
          message: error?.message || "Django REST Framework API is not reachable.",
        },
      },
      { status: 502 }
    );
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const params = await context.params;
  return proxyRequest(request, params);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const params = await context.params;
  return proxyRequest(request, params);
}

export async function PUT(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const params = await context.params;
  return proxyRequest(request, params);
}

export async function PATCH(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const params = await context.params;
  return proxyRequest(request, params);
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const params = await context.params;
  return proxyRequest(request, params);
}
