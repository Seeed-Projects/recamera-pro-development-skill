#include <gst/app/gstappsink.h>
#include <gst/gst.h>
#include <rknn_api.h>

#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static std::vector<uint8_t> read_file(const std::string& path) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) throw std::runtime_error("cannot open model: " + path);
  const auto size = input.tellg();
  if (size <= 0) throw std::runtime_error("empty model: " + path);
  std::vector<uint8_t> data(static_cast<size_t>(size));
  input.seekg(0);
  input.read(reinterpret_cast<char*>(data.data()), size);
  if (!input) throw std::runtime_error("cannot read model: " + path);
  return data;
}

static void require_rknn(int code, const char* operation) {
  if (code != RKNN_SUCC) throw std::runtime_error(std::string(operation) + " failed: " + std::to_string(code));
}

int main(int argc, char** argv) {
  if (argc != 4) {
    std::cerr << "usage: " << argv[0] << " MODEL.rknn INPUT_WIDTH INPUT_HEIGHT\n";
    return 2;
  }

  const int width = std::stoi(argv[2]);
  const int height = std::stoi(argv[3]);
  if (width <= 0 || height <= 0) throw std::runtime_error("input dimensions must be positive");

  gst_init(&argc, &argv);
  rknn_context context = 0;
  GstElement* pipeline = nullptr;
  GstSample* sample = nullptr;

  try {
    auto model = read_file(argv[1]);
    require_rknn(rknn_init(&context, model.data(), model.size(), 0, nullptr), "rknn_init");

    rknn_input_output_num count{};
    require_rknn(rknn_query(context, RKNN_QUERY_IN_OUT_NUM, &count, sizeof(count)), "query io count");
    if (count.n_input != 1) throw std::runtime_error("starter supports exactly one input tensor");

    rknn_tensor_attr input_attr{};
    input_attr.index = 0;
    require_rknn(rknn_query(context, RKNN_QUERY_INPUT_ATTR, &input_attr, sizeof(input_attr)), "query input");

    const std::string description =
        "v4l2src device=/dev/video13 ! "
        "video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1 ! "
        "videoconvert ! videoscale ! video/x-raw,format=RGB,width=" + std::to_string(width) +
        ",height=" + std::to_string(height) + " ! "
        "appsink name=inference_sink max-buffers=1 drop=true sync=false";
    GError* error = nullptr;
    pipeline = gst_parse_launch(description.c_str(), &error);
    if (!pipeline) {
      const std::string message = error ? error->message : "unknown GStreamer error";
      if (error) g_error_free(error);
      throw std::runtime_error("pipeline creation failed: " + message);
    }
    GstElement* sink = gst_bin_get_by_name(GST_BIN(pipeline), "inference_sink");
    if (!sink) throw std::runtime_error("appsink not found");
    if (gst_element_set_state(pipeline, GST_STATE_PLAYING) == GST_STATE_CHANGE_FAILURE)
      throw std::runtime_error("pipeline failed to enter PLAYING");

    sample = gst_app_sink_try_pull_sample(GST_APP_SINK(sink), 5 * GST_SECOND);
    gst_object_unref(sink);
    if (!sample) throw std::runtime_error("timed out waiting for video frame");

    GstBuffer* buffer = gst_sample_get_buffer(sample);
    GstMapInfo map{};
    if (!gst_buffer_map(buffer, &map, GST_MAP_READ)) throw std::runtime_error("cannot map video frame");

    rknn_input input{};
    input.index = 0;
    input.type = RKNN_TENSOR_UINT8;
    input.fmt = RKNN_TENSOR_NHWC;
    input.size = map.size;
    input.buf = map.data;
    input.pass_through = 0;
    if (map.size != static_cast<size_t>(width * height * 3)) {
      gst_buffer_unmap(buffer, &map);
      throw std::runtime_error("RGB frame size does not match requested dimensions");
    }
    require_rknn(rknn_inputs_set(context, 1, &input), "rknn_inputs_set");
    require_rknn(rknn_run(context, nullptr), "rknn_run");

    std::vector<rknn_output> outputs(count.n_output);
    for (auto& output : outputs) output.want_float = 1;
    require_rknn(rknn_outputs_get(context, count.n_output, outputs.data(), nullptr), "rknn_outputs_get");
    for (uint32_t i = 0; i < count.n_output; ++i)
      std::cout << "output[" << i << "] bytes=" << outputs[i].size << '\n';
    require_rknn(rknn_outputs_release(context, count.n_output, outputs.data()), "rknn_outputs_release");
    gst_buffer_unmap(buffer, &map);

    gst_sample_unref(sample);
    gst_element_set_state(pipeline, GST_STATE_NULL);
    gst_object_unref(pipeline);
    rknn_destroy(context);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "error: " << error.what() << '\n';
    if (sample) gst_sample_unref(sample);
    if (pipeline) {
      gst_element_set_state(pipeline, GST_STATE_NULL);
      gst_object_unref(pipeline);
    }
    if (context) rknn_destroy(context);
    return 1;
  }
}
